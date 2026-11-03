"""DES-04 Context Pack contracts: deterministic, bounded and fail-closed."""
from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pie.indexing.indexer import index_project
from pie.interfaces.cli import command_init
from pie.interfaces.mcp_server import dispatch
from pie.retrieval.context_pack import build_context_pack
from pie.retrieval.evidence import EvidenceError


class ContextPackContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "logic.py").write_text(
            "def calculate(value):\n"
            "    return value + 1\n", encoding="utf-8")
        (self.root / "service.py").write_text(
            "from logic import calculate\n"
            "def run():\n"
            "    return calculate(2)\n", encoding="utf-8")
        command_init(self.root)
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")

    def tearDown(self):
        self.temp.cleanup()

    def test_definition_callers_and_source_provenance(self):
        result = build_context_pack(self.root, "calculate")
        self.assertEqual(result["schema_version"], "pie-context-pack-v2")
        self.assertEqual(result["status"], "VERIFIED_STATIC_CONTEXT")
        self.assertEqual(result["definition"]["path"], "logic.py")
        self.assertEqual(result["definition"]["line"], 1)
        self.assertIn("def calculate(value)", result["definition"]["snippet"]["text"])
        self.assertEqual(result["coverage"]["verified_direct_call_count"], 1)
        self.assertTrue(result["coverage"]["returned_verified_call_list_complete"])
        self.assertEqual(result["coverage"]["static_analysis_coverage"], "PARTIAL")
        self.assertFalse(result["coverage"]["exhaustive"])
        self.assertEqual(len(result["callers"]), 1)
        caller = result["callers"][0]
        self.assertEqual((caller["path"], caller["line"]), ("service.py", 3))
        self.assertEqual(caller["resolution"], "verified")
        self.assertEqual(caller["usage_kind"], "direct_call")
        self.assertEqual(result["impact"]["status"], "UNDETERMINED")
        self.assertNotIn("model", result)

    def test_budget_is_hard_and_deterministic(self):
        first = build_context_pack(self.root, "calculate", max_chars=1500)
        second = build_context_pack(self.root, "calculate", max_chars=1500)
        self.assertEqual(first, second)
        size = len(json.dumps(first, ensure_ascii=False, separators=(",", ":")))
        self.assertEqual(first["budget"]["used_chars"], size)
        self.assertLessEqual(size, 1500)
        self.assertEqual(first["budget"]["unit"], "serialized_json_characters_not_model_tokens")

    def test_budget_omissions_are_explicit(self):
        (self.root / "service.py").write_text(
            "from logic import calculate\n"
            "def run():\n" +
            "".join(f"    calculate({i})\n" for i in range(50)),
            encoding="utf-8")
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")
        report = build_context_pack(self.root, "calculate", max_chars=1800)
        coverage = report["coverage"]
        self.assertEqual(coverage["verified_direct_call_count"], 50)
        self.assertEqual(coverage["returned_direct_call_count"], len(report["callers"]))
        self.assertGreater(coverage["omitted_by_budget"], 0)
        self.assertEqual(coverage["omitted_by_budget"] + coverage["returned_direct_call_count"], 50)
        self.assertFalse(coverage["returned_verified_call_list_complete"])
        self.assertLessEqual(report["budget"]["used_chars"], 1800)

    def test_call_limit_omission_is_not_hidden(self):
        (self.root / "service.py").write_text(
            "from logic import calculate\n"
            "def run():\n" +
            "".join(f"    calculate({i})\n" for i in range(7)),
            encoding="utf-8")
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")
        report = build_context_pack(self.root, "calculate", max_calls=2)
        self.assertEqual(report["coverage"]["verified_direct_call_count"], 7)
        self.assertEqual(report["coverage"]["omitted_by_call_limit"], 5)
        self.assertEqual(report["coverage"]["returned_direct_call_count"], 2)
        self.assertFalse(report["coverage"]["returned_verified_call_list_complete"])

    def test_stale_and_ambiguous_fail_closed(self):
        (self.root / "new_caller.py").write_text(
            "from logic import calculate\ncalculate(100)\n", encoding="utf-8")
        with self.assertRaisesRegex(EvidenceError, "STALE_PROJECT"):
            build_context_pack(self.root, "calculate")
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")
        (self.root / "alternate.py").write_text(
            "def calculate(x):\n    return x\n", encoding="utf-8")
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")
        with self.assertRaisesRegex(EvidenceError, "AMBIGUOUS"):
            build_context_pack(self.root, "calculate")

    def test_strict_input_contract(self):
        for args in ({"max_chars": True}, {"max_chars": 100},
                     {"max_calls": False}, {"include_snippets": "false"}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                build_context_pack(self.root, "calculate", **args)

    def test_cli_context_pack_emits_json(self):
        from pie.interfaces.cli import main
        output = StringIO()
        with redirect_stdout(output):
            code = main([
                "context-pack", "calculate", "--root", str(self.root),
                "--max-chars", "3000",
            ])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["definition"]["symbol"], "calculate")
        self.assertEqual(result["callers"][0]["line"], 3)

    def test_mcp_rejects_stale_project(self):
        (self.root / "not_indexed.py").write_text(
            "from logic import calculate\ncalculate(4)\n", encoding="utf-8")
        reply = dispatch({
            "jsonrpc": "2.0", "id": 77, "method": "tools/call",
            "params": {"name": "pie_build_context_pack",
                       "arguments": {"symbol": "calculate"}},
        }, self.root)
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("STALE_PROJECT", reply["result"]["content"][0]["text"])

    def test_mcp_exposes_pack_and_rejects_untrusted_arguments(self):
        listed = dispatch({"jsonrpc":"2.0", "id":1, "method":"tools/list"}, self.root)
        tool = next(x for x in listed["result"]["tools"] if x["name"] == "pie_build_context_pack")
        self.assertEqual(tool["inputSchema"]["required"], ["symbol"])
        request = {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "pie_build_context_pack",
                       "arguments": {"symbol": "calculate", "max_chars": 3000}},
        }
        reply = dispatch(request, self.root)
        self.assertNotIn("error", reply)
        self.assertFalse(reply["result"].get("isError", False))
        payload = json.loads(reply["result"]["content"][0]["text"])
        self.assertEqual(payload["definition"]["symbol"], "calculate")
        request["params"]["arguments"]["root"] = "/another/workspace"
        rejected = dispatch(request, self.root)
        self.assertTrue(rejected["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
