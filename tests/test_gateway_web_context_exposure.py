from __future__ import annotations

import io
import json
from pathlib import Path
import sys

from pie.gateway.mcp_stdio import MCPStdioGateway
from pie.gateway.web_results import WEB_CONTEXT_NAME


def _listed(gateway: MCPStdioGateway, exposed_tools: tuple[str, ...]) -> set[str]:
    gateway.exposed_tools = frozenset(exposed_tools)
    response = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"tools": [{"name": "browser_snapshot"}]},
    }
    transformed = gateway._transform(response)
    return {item["name"] for item in transformed["result"]["tools"]}


def test_web_context_is_not_announced_by_default(tmp_path: Path):
    gateway = MCPStdioGateway(tmp_path, ["python"], profile="web")
    assert WEB_CONTEXT_NAME not in _listed(gateway, ())


def test_web_context_is_announced_when_explicitly_exposed(tmp_path: Path):
    gateway = MCPStdioGateway(tmp_path, ["python"], profile="web")
    assert WEB_CONTEXT_NAME in _listed(
        gateway, ("browser_snapshot", WEB_CONTEXT_NAME)
    )


def _fake_upstream(tmp_path: Path) -> Path:
    script = tmp_path / "fake_web_upstream.py"
    script.write_text(
        """
import json
import sys

snapshot = "### Snapshot\\n- heading \\\"Notas locais\\\" [level=1]\\n- textbox \\\"Pesquisar\\\" [ref=e3]\\n- status \\\"Pronto\\\"\\n"
for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if method == "notifications/initialized":
        continue
    if method == "initialize":
        result = {"protocolVersion": "2025-03-26", "capabilities": {}}
    elif method == "tools/list":
        result = {"tools": [{"name": "browser_snapshot"}]}
    elif method == "tools/call" and request.get("params", {}).get("name") == "browser_snapshot":
        result = {"content": [{"type": "text", "text": snapshot}]}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": request.get("id"),
                          "error": {"code": -32601, "message": "unknown tool"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": request.get("id"),
                      "result": result}), flush=True)
""",
        encoding="utf-8",
    )
    return script


def _run_gateway(tmp_path: Path, exposed_tools: tuple[str, ...], calls: list[dict]) -> list[dict]:
    gateway = MCPStdioGateway(
        tmp_path,
        [sys.executable, str(_fake_upstream(tmp_path))],
        profile="web",
        exposed_tools=exposed_tools,
    )
    payload = "\n".join(json.dumps(item) for item in calls) + "\n"
    output = io.StringIO()
    assert gateway.run(io.StringIO(payload), output) == 0
    return [json.loads(line) for line in output.getvalue().splitlines() if line]


def test_explicit_web_context_call_is_intercepted_locally(tmp_path: Path):
    rows = _run_gateway(
        tmp_path,
        ("browser_snapshot", WEB_CONTEXT_NAME),
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "browser_snapshot", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": WEB_CONTEXT_NAME, "arguments": {"query": "Pesquisar"}}},
        ],
    )
    context = next(row for row in rows if row.get("id") == 4)
    payload = json.loads(context["result"]["content"][0]["text"])
    assert payload["schema"] == "pie-web-context-v1"
    assert "Pesquisar" in payload["preview"]


def test_hidden_web_context_call_is_rejected_by_allowlist(tmp_path: Path):
    rows = _run_gateway(
        tmp_path,
        ("browser_snapshot",),
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": WEB_CONTEXT_NAME, "arguments": {"query": "Pesquisar"}}},
        ],
    )
    rejected = next(row for row in rows if row.get("id") == 2)
    assert rejected["result"]["isError"] is True
    assert rejected["result"]["content"][0]["text"] == "PIE_TOOL_NOT_EXPOSED"
