"""Caveman-style structured unittest compaction; no provider calls."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from caveman_testreport_adapter import compact_unittest_success

GOOD="""test_retry_limit (test_checkout.Tests.test_retry_limit) ... ok
test_retry_success (test_checkout.Tests.test_retry_success) ... ok
test_rollback_on_failure (test_checkout.Tests.test_rollback_on_failure) ... ok
test_nonretryable_error (test_checkout.Tests.test_nonretryable_error) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.001s

OK
"""

class CavemanAdapterTests(unittest.TestCase):
    def test_all_test_names_survive(self):
        out=compact_unittest_success(GOOD)
        self.assertEqual(out["state"],"COMPLETE")
        self.assertEqual(out["covered"],4)
        self.assertLess(len(out["text"]),len(GOOD))
        for case in ("test_retry_limit","test_retry_success","test_rollback_on_failure","test_nonretryable_error"):
            self.assertIn(case,out["text"])

    def test_failure_passes_through(self):
        report=GOOD.replace("... ok","... FAIL",1).replace("\nOK\n","\nFAILED (failures=1)\n")
        out=compact_unittest_success(report)
        self.assertEqual(out["state"],"PASSTHROUGH")
        self.assertEqual(out["text"],report)

    def test_unknown_and_malformed_pass_through(self):
        for value in ("unrecognized", GOOD.replace("Ran 4","Ran 3"), GOOD.replace("OK\n","")):
            self.assertEqual(compact_unittest_success(value)["state"],"PASSTHROUGH")

    def test_non_text_rejected(self):
        with self.assertRaises(TypeError):
            compact_unittest_success(None)

if __name__=="__main__": unittest.main()
