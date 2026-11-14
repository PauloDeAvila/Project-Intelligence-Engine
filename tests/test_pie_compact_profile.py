"""Compact MCP tool profile: smaller discovery without changing full defaults."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pie.interfaces.mcp_server import dispatch, COMPACT_TOOL_NAMES
from pie.interfaces.setup import provision


class CompactMcpTests(unittest.TestCase):
    def test_tool_schema_reduction_is_labeled_characters_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            request={"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
            full=dispatch(request,root)["result"]["tools"]
            compact=dispatch(request,root,tool_profile="compact")["result"]["tools"]
            self.assertEqual({t["name"] for t in compact}, set(COMPACT_TOOL_NAMES))
            self.assertTrue(len(compact)<len(full))
            original_chars=len(json.dumps(full,separators=(",",":")))
            compact_chars=len(json.dumps(compact,separators=(",",":")))
            self.assertLess(compact_chars,original_chars)
            self.assertGreater(original_chars-compact_chars,1000)

    def test_hidden_full_tool_rejected_in_compact_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            req={"jsonrpc":"2.0","id":4,"method":"tools/call",
                 "params":{"name":"pie_search_symbols","arguments":{"query":"Cache"}}}
            result=dispatch(req,root,tool_profile="compact")["result"]
            self.assertTrue(result["isError"])

    def test_setup_writes_profile_for_codex_in_opt_in_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"main.py").write_text("def hello():\n    return 1\n",encoding="utf8")
            result=provision(root, clients=("codex",),tool_profile="compact")
            self.assertEqual(result["index_state"],"CURRENT")
            data=(root/".codex"/"config.toml").read_text(encoding="utf8")
            self.assertIn('"--tool-profile", "compact"',data)
            self.assertIn("mcp_servers.pie-",data)
            # Repeated setup must remain idempotent.
            again=provision(root,clients=("codex",),tool_profile="compact")
            self.assertEqual(again["clients"]["codex"]["status"],"unchanged")


if __name__=="__main__":
    unittest.main()
