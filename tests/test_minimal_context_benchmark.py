"""Isolated regression of the minimal-context selector and experiment budget."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"src"))
from benchmark_minimal_context import minimal_evidence, bench


class MinimalContextTests(unittest.TestCase):
    def report(self):
        return {"context_state":"CURRENT","omitted":[],"evidence":[
            {"kind":"definition","symbol":"A","path":"a.py","start_line":1,"end_line":1,"content":"A=1"},
            *[{"kind":"function","symbol":f"f{i}","path":"a.py","start_line":i+1,"end_line":i+1,"content":f"def f{i}():pass"} for i in range(6)],
            *[{"kind":"behavioral_test","symbol":f"t{i}","path":"tests/test_a.py","start_line":i+1,"end_line":i+1,"content":f"def t{i}():pass"} for i in range(2)]
        ]}

    def test_selects_complete_ranked_blocks(self):
        r=self.report()
        s=minimal_evidence(r,functions=2,tests=1)
        self.assertEqual([x["symbol"] for x in s["evidence"]],["A","f0","f1","t0"])
        self.assertEqual(s["dropped_existing_candidates"],5)
        self.assertEqual(len(r["evidence"]),9)  # does not mutate existing mode

    def test_stale_or_partial_refused(self):
        for patch_data in ({"context_state":"STALE"},{"omitted":[{"reason":"budget"}]}):
            with self.assertRaises(ValueError):
                minimal_evidence({**self.report(),**patch_data})

    def test_bad_caps_refused(self):
        for kwargs in ({"functions":0},{"functions":10},{"tests":3}):
            with self.assertRaises(ValueError):
                minimal_evidence(self.report(),**kwargs)

    def test_budget_refuses_extra_inference(self):
        args=argparse.Namespace(max_calls=5,cases="MAX_RETRIES,release",repeats=1,scale_modules=0)
        with self.assertRaises(ValueError):
            bench(args)

    def test_dry_run_uses_no_network_and_real_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=argparse.Namespace(max_calls=4,cases="MAX_RETRIES,release",repeats=1,
                scale_modules=0,out=tmp,model="gh/gpt-4o-mini",functions=3,tests=1,
                dry_run=True,cooldown=10,max_tokens=768)
            with patch.dict(os.environ,{"PIE_API_BASE_URL":"","PIE_API_KEY":""}):
                outcome=bench(args)
            self.assertEqual(outcome["api_calls"],0)
            aud=json.loads((Path(tmp)/"audit.json").read_text(encoding="utf-8"))["audit"]
            self.assertEqual(len(aud),2)
            for item in aud.values():
                self.assertLess(item["minimal_chars"],item["original_chars"])


if __name__=="__main__":
    unittest.main()
