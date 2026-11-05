"""Safety checks for a <=5-call 9Router/NVIDIA benchmark."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import cloud_pie_benchmark as bench


class FiveCallBudgetTests(unittest.TestCase):
    def invoke(self,*extra):
        with tempfile.TemporaryDirectory() as td:
            argv=["cloud_pie_benchmark.py","--dry-run",
                  "--out",str(Path(td)/"evidence"),*extra]
            with patch.object(sys,"argv",argv),patch.dict(os.environ,{"PIE_API_BASE_URL":"","PIE_API_KEY":""}):
                with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                    bench.run()

    def test_rejects_excess_call_plan_before_network_or_index(self):
        with patch.object(bench,"index_project",side_effect=AssertionError("must not index")):
            with self.assertRaises(SystemExit) as err:
                self.invoke("--cases","MAX_RETRIES,release,charge_with_retry",
                            "--modes","baseline,pie_rtk","--max-calls","5")
        self.assertEqual(err.exception.code,2)

    def test_rejects_attempt_limit_above_five(self):
        with self.assertRaises(SystemExit) as err:
            self.invoke("--cases","MAX_RETRIES,release",
                        "--modes","baseline,pie_rtk","--max-calls","6")
        self.assertEqual(err.exception.code,2)

    def test_rejects_fast_burst(self):
        with self.assertRaises(SystemExit) as err:
            self.invoke("--cases","MAX_RETRIES,release",
                        "--modes","baseline,pie_rtk",
                        "--max-calls","5","--cooldown-seconds","0")
        self.assertEqual(err.exception.code,2)

    def test_rejects_duplicate_case(self):
        with self.assertRaises(SystemExit) as err:
            self.invoke("--cases","MAX_RETRIES,MAX_RETRIES",
                        "--modes","baseline,pie_rtk")
        self.assertEqual(err.exception.code,2)

    def test_four_call_preflight_makes_zero_requests(self):
        with patch.object(bench,"call",side_effect=AssertionError("API should not be called")):
            self.invoke("--cases","MAX_RETRIES,release","--modes","baseline,pie_rtk",
                        "--max-calls","5","--cooldown-seconds","10")


if __name__=="__main__":
    unittest.main()
