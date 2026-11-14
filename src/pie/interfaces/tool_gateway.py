"""Bounded, allowlisted PIE Tool Gateway for read-only local operations.

MCP tool calls are explicitly routed, not transparent capture of external agents.
No shell commands, arbitrary file paths, URLs, dynamic imports or remote calls.
"""
from __future__ import annotations

import json
from contextlib import closing
from pie.storage.locations import workspace_file
from pie.storage.database import connect
from pathlib import Path
from typing import Any

from pie.retrieval.output_pipeline import compact_output, recover_output

OPERATIONS = {
    "project_status": {"required": (), "optional": ()},
    "source_query": {"required": ("query",), "optional": ("mode", "limit", "max_chars")},
    "task_search": {"required": ("query",), "optional": ("limit", "max_chars")},
    "task_resume": {"required": (), "optional": ("task_id", "limit")},
    "context_pack": {"required": ("symbol",), "optional": ("max_chars", "max_calls")},
    "output_compact": {"required": ("text",), "optional": ("kind", "exit_code", "max_chars")},
    "output_get": {"required": ("output_id",), "optional": ("start", "max_chars")},
}
MAX_INLINE = 64000


def _validate(op: str, arguments: dict, max_chars: int) -> None:
    if op not in OPERATIONS:
        raise ValueError("Gateway operation not allowlisted")
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    spec = OPERATIONS[op]
    allowed = set(spec["required"]) | set(spec["optional"])
    if set(arguments) - allowed or any(k not in arguments for k in spec["required"]):
        raise ValueError("Gateway arguments do not match operation contract")
    if type(max_chars) is not int or not 512 <= max_chars <= MAX_INLINE:
        raise ValueError("max_chars must be 512..64000")
    for key,value in arguments.items():
        if key in ("limit","max_chars","max_calls","exit_code","start"):
            if type(value) is not int:
                raise ValueError(f"{key} must be an integer")
        elif not isinstance(value,str) or not value.strip() or "\x00" in value:
            raise ValueError(f"{key} must be a nonempty safe string")
        if isinstance(value,str) and len(value)>4096:
            raise ValueError(f"{key} is too long")
    if "start" in arguments and arguments["start"] < 0:
        raise ValueError("start cannot be negative")
    if "limit" in arguments and not 1 <= arguments["limit"] <= (100 if op=="task_resume" else 20):
        raise ValueError("limit out of range")
    if "max_calls" in arguments and not 1<=arguments["max_calls"]<=100:
        raise ValueError("max_calls out of range")
    if "max_chars" in arguments and not (256 if op=="output_compact" else 500) <= arguments["max_chars"] <= MAX_INLINE:
        raise ValueError("operation max_chars out of range")
    if op=="task_search" and "max_chars" in arguments and arguments["max_chars"] < 1000:
        raise ValueError("task_search max_chars must be >=1000")
    if op=="context_pack" and "max_chars" in arguments and arguments["max_chars"] < 1500:
        raise ValueError("context_pack max_chars must be >=1500")
    if op=="output_compact" and "exit_code" in arguments and not -65535<=arguments["exit_code"]<=65535:
        raise ValueError("exit_code out of range")
    if op=="output_compact" and arguments.get("kind","log") not in ("log","test","git","terminal","web","api"):
        raise ValueError("invalid kind")
    if op=="source_query" and arguments.get("mode","responsibility") not in ("responsibility","navigation","impact"):
        raise ValueError("invalid query mode")



def _source_manifest(root: Path, result: dict) -> list[dict]:
    """Bind source/query recovery to the actual currently indexed Python files."""
    paths = set()
    def walk(value, depth=0):
        if depth > 18 or len(paths) > 128:
            return
        if isinstance(value, dict):
            item = value.get("path")
            if isinstance(item, str) and item.endswith(".py"):
                paths.add(item)
            for child in value.values():
                if isinstance(child, (dict, list)):
                    walk(child, depth + 1)
        elif isinstance(value, list):
            for child in value[:200]:
                walk(child, depth + 1)
    walk(result)
    if len(paths) > 128:
        raise ValueError("Too many source references; narrow the query")
    if not paths:
        return []
    root = Path(root).resolve(strict=True)
    with closing(connect(workspace_file(root))) as db:
        result = []
        for path in sorted(paths):
            row = db.execute("SELECT sha256 FROM files WHERE path=?", (path,)).fetchone()
            if not row:
                raise ValueError("Source reference not indexed or stale")
            result.append({"path": path, "sha256": row["sha256"]})
    return result


def _page_recovery(root: Path, output_id: str, start: int, max_chars: int) -> dict:
    """Bound the complete response envelope and report every omitted character."""
    source = recover_output(root, output_id)
    full = source["text"]
    if start > len(full):
        raise ValueError("Recovery start exceeds stored text")
    step = max(0, max_chars - 550)
    while True:
        end = min(start + step, len(full))
        source["text"] = full[start:end]
        source["state"] = "COMPLETE_SANITIZED" if start == 0 and end == len(full) else "PARTIAL"
        source.update({"start": start, "end": end, "total_chars": len(full),
                       "remaining_chars": len(full) - end})
        envelope = {"operation":"output_get","state":source["state"],"result":source}
        length = len(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
        if length <= max_chars and (end > start or start == len(full)):
            return envelope
        if step == 0:
            raise ValueError("Recovery budget cannot fit metadata")
        step = max(0, step - max(1, length - max_chars))

def execute_gateway(root: Path, operation: str, arguments: dict | None = None,
                    *, max_chars: int = 4000, engine=None) -> dict[str, Any]:
    """Perform an explicitly requested read-only operation.

    For large responses, return a recovery handle and no clipped claims.
    Store a sanitized original as long as result is within the storage ceiling.
    """
    args = {} if arguments is None else arguments
    _validate(operation, args, max_chars)
    if operation=="output_get":
        # Exact sanitized recovery; page rather than exceeding the gateway budget.
        return _page_recovery(root,args["output_id"],args.get("start",0),
                              min(max_chars,args.get("max_chars",max_chars)))
    if operation=="output_compact":
        data=compact_output(root,args["text"],kind=args.get("kind","log"),
                            max_chars=args.get("max_chars",max_chars),
                            exit_code=args.get("exit_code"))
        return {"operation":operation,"state":data["state"],"result":data}
    if operation=="project_status":
        from pie.interfaces.cli import command_status
        result=command_status(root)
    elif operation=="source_query":
        from pie.interfaces.mcp_context import MCPContextEngine
        if engine is None:
            with MCPContextEngine(root) as local:
                result=local.query(args["query"],mode=args.get("mode","responsibility"),
                                   limit=args.get("limit",5),
                                   max_chars=args.get("max_chars",12000))
        else:
            result=engine.query(args["query"],mode=args.get("mode","responsibility"),
                                limit=args.get("limit",5),
                                max_chars=args.get("max_chars",12000))
    elif operation=="task_search":
        from pie.retrieval.task_search import search_tasks
        result=search_tasks(root,args["query"],limit=args.get("limit",10),
                            max_chars=args.get("max_chars",12000))
    elif operation=="task_resume":
        from pie.retrieval.task_memory import resume_task
        result=resume_task(root,args.get("task_id"),args.get("limit",30))
    elif operation=="context_pack":
        from pie.retrieval.context_pack import build_context_pack
        result=build_context_pack(root,args["symbol"],max_chars=args.get("max_chars",12000),
                                  max_calls=args.get("max_calls",100))
    else:
        raise ValueError("Unexpected gateway operation")

    payload=json.dumps(result,ensure_ascii=False,separators=(",",":"))
    if len(payload)>500000:
        # Explicit refusal rather than silently losing a huge response or
        # causing unbounded local storage. Caller may narrow the query.
        raise ValueError("Gateway source output exceeds storage ceiling; narrow the request")
    manifest = _source_manifest(root, result) if operation in ("source_query","context_pack") else []
    stored=compact_output(root,payload,kind="api",max_chars=512,source_manifest=manifest)
    sanitized=recover_output(root,stored["output_id"])["text"]
    metadata={"output_id":stored["output_id"],"source_chars":len(sanitized),
              "sha256":stored["sha256"],"redacted_before_storage":True,
              "measurement":"characters_not_tokens",
              "verified_source_files":len(manifest)}
    # Hard bound includes the actual JSON envelope, not only the source payload.
    envelope={"operation":operation,"state":"COMPLETE","result":sanitized,
              "telemetry":metadata}
    serialized=lambda v: json.dumps(v,ensure_ascii=False,separators=(",",":"))
    if len(serialized(envelope)) <= max_chars:
        return envelope
    compact={"operation":operation,"state":"PARTIAL","result":None,
             "telemetry":metadata,
             "reason":"Result withheld due to hard max_chars budget; call output_get with output_id or refine query."}
    if len(serialized(compact))>max_chars:
        raise ValueError("Gateway metadata exceeds budget")
    return compact
