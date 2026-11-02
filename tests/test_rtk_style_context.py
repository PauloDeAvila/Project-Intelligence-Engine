"""Tests for loss-aware RTK-style presentation and output compression."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from rtk_style_context import compress_tool_output, compact_source_evidence, python_outline

class RTKStyleTests(unittest.TestCase):
    def test_duplicate_failures_retained_once_with_count(self):
        data = "ERROR connection failed\nERROR connection failed\nOK\n"
        output=compress_tool_output(data,kind="pytest")
        self.assertEqual(output["state"], "COMPLETE")
        self.assertIn("repeated 2x",output["output"])
        self.assertIn("ERROR connection failed",output["output"])
    def test_truncation_is_explicit(self):
        data="\n".join("ERROR "+str(i)+" "+("a"*100) for i in range(20))
        result=compress_tool_output(data,max_chars=350)
        self.assertEqual(result["state"], "PARTIAL")
        self.assertGreater(result["omitted_unique"],0)
    def test_secrets_masked(self):
        result=compress_tool_output("Authorization: Bearer secretvalue123456789")
        self.assertNotIn("secretvalue123456789",result["output"])
    def test_source_dedup_and_exact_content(self):
        item={"path":"p.py","start_line":1,"end_line":2,
              "symbol":"myfunc","content":"def myfunc():\n    raise ValueError()"}
        result=compact_source_evidence({"context_state":"CURRENT","evidence":[item,item]})
        self.assertEqual(result["content"].count("def myfunc():"),1)
        self.assertIn("raise ValueError()",result["content"])
        self.assertEqual(result["state"],"CURRENT")
    def test_source_budget_fail_closed_partial(self):
        item={"path":"p.py","start_line":1,"end_line":2,"content":"x="+"a"*700}
        result=compact_source_evidence({"context_state":"CURRENT","evidence":[item]},max_chars=500)
        self.assertEqual(result["state"],"PARTIAL")
        self.assertEqual(len(result["omitted"]),1)
    def test_stale_rejected(self):
        with self.assertRaises(ValueError):
            compact_source_evidence({"context_state":"STALE","evidence":[]})
    def test_python_outline_no_bodies(self):
        src="class C:\n    def change(self, x):\n        return x + 1\n"
        result=python_outline(src,"x.py")
        self.assertIn("class C",result)
        self.assertIn("def change",result)
        self.assertNotIn("return x",result)

if __name__ == "__main__":
    unittest.main()
