from __future__ import annotations

from pathlib import Path

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
