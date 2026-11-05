"""Bounded, allowlisted PIE Tool Gateway for read-only local operations.

MCP tool calls are explicitly routed, not transparent capture of external agents.
No shell commands, arbitrary file paths, URLs, dynamic imports or remote calls.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pie.retrieval.output_pipeline import compact_output, recover_output

OPERATIONS = {
    "project_status": {"required": (), "optional": ()},
    "graph_rank": {"required": ("query",), "optional": ("limit", "max_chars", "candidates")},
    "blast_diff": {"required": (), "optional": ("depth", "limit", "max_chars")},
    "source_query": {"required": ("query",), "optional": ("mode", "limit", "max_chars")},
    "task_search": {"required": ("query",), "optional": ("limit", "max_chars")},
    "task_resume": {"required": (), "optional": ("task_id", "limit")},
    "context_pack": {"required": ("symbol",), "optional": ("max_chars", "max_calls")},
    "output_compact": {"required": ("text",), "optional": ("kind", "exit_code", "max_chars")},
    "output_get": {"required": ("output_id",), "optional": ()},
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
        if key in ("limit","max_chars","max_calls","exit_code","depth","candidates"):
            if type(value) is not int:
                raise ValueError(f"{key} must be an integer")
        elif not isinstance(value,str) or not value.strip() or "\x00" in value:
            raise ValueError(f"{key} must be a nonempty safe string")
        if isinstance(value,str) and len(value)>4096:
            raise ValueError(f"{key} is too long")
    if "limit" in arguments and not 1 <= arguments["limit"] <= (100 if op in ("task_resume","blast_diff") else 20):
        raise ValueError("limit out of range")
    if "depth" in arguments and not 0<=arguments["depth"]<=5:
        raise ValueError("depth out of range")
    if "candidates" in arguments and not arguments.get("limit",5)<=arguments["candidates"]<=100:
        raise ValueError("candidates out of range")
    if "max_calls" in arguments and not 1<=arguments["max_calls"]<=100:
        raise ValueError("max_calls out of range")
    if "max_chars" in arguments and not (256 if op=="output_compact" else 500) <= arguments["max_chars"] <= MAX_INLINE:
        raise ValueError("operation max_chars out of range")
    if op in ("graph_rank","blast_diff") and "max_chars" in arguments and arguments["max_chars"] < 1000:
        raise ValueError("ranking/impact max_chars must be >=1000")
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


def execute_gateway(root: Path, operation: str, arguments: dict | None = None,
                    *, max_chars: int = 4000, engine=None) -> dict[str, Any]:
    """Perform an explicitly requested read-only operation.

    For large responses, return a recovery handle and no clipped claims.
    Store a sanitized original as long as result is within the storage ceiling.
    """
    args = {} if arguments is None else arguments
    _validate(operation, args, max_chars)
    if operation=="output_get":
        # Exact sanitized recovery: no recursive re-storage or re-compaction.
        return {"operation":operation,"state":"COMPLETE_SANITIZED",
                "result":recover_output(root,args["output_id"])}
    if operation=="output_compact":
        data=compact_output(root,args["text"],kind=args.get("kind","log"),
                            max_chars=args.get("max_chars",max_chars),
                            exit_code=args.get("exit_code"))
        return {"operation":operation,"state":data["state"],"result":data}
    if operation=="graph_rank":
        from pie.retrieval.graph_rank import rank_context
        result=rank_context(root,args["query"],limit=args.get("limit",5),max_chars=args.get("max_chars",12000),candidates=args.get("candidates",40))
    elif operation=="blast_diff":
        from pie.retrieval.diff_blast import blast_diff
        result=blast_diff(root,depth=args.get("depth",2),limit=args.get("limit",50),max_chars=args.get("max_chars",16000))
    elif operation=="project_status":
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
    stored=compact_output(root,payload,kind="api",max_chars=512)
    sanitized=recover_output(root,stored["output_id"])["text"]
    metadata={"output_id":stored["output_id"],"source_chars":len(sanitized),
              "sha256":stored["sha256"],"redacted_before_storage":True,
              "measurement":"characters_not_tokens"}
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
