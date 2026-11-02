"""Regression tests for auditable PIE metrics and missing token usage."""
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class ReportTests(unittest.TestCase):
    def generate(self, rows):
        folder = tempfile.TemporaryDirectory()
        base = Path(folder.name)
        source = base / "results.json"
        source.write_text(json.dumps({"results": rows}), encoding="utf8")
        process = subprocess.run([sys.executable, "tools/pie_agent_report.py",
            "--input", str(source), "--out", str(base / "output")],
            capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        summary = json.loads((base / "output" / "summary.json").read_text())
        with (base / "output" / "attempts.csv").open(newline="") as stream:
            details = list(csv.DictReader(stream))
        folder.cleanup()
        return summary, details

    def test_missing_and_valid_usage_are_distinct(self):
        summary, details = self.generate([
            {"task": 0, "mode": "pie", "model": "qd/qfmodel", "ok": True,
             "correct": True, "calls": 2, "prompt_tokens": 300, "completion_tokens": 40,
             "searches": 1, "model_ms": [100, 110], "search_ms": [25]},
            {"task": 0, "mode": "baseline", "model": "qd/qfmodel", "ok": False,
             "error": "HTTPError", "error_detail": "HTTP Error 429", "http_status": 429}])
        self.assertEqual(summary["attempts"], 2)
        self.assertEqual(summary["failures"], 1)
        self.assertEqual(summary["http_failures"], 1)
        self.assertEqual(summary["completed_pairs"], 0)
        self.assertIsNone(summary["input_token_saving_pct"])
        self.assertEqual(summary["retrieval_mean_ms"], 25)
        self.assertEqual(details[0]["model_ms_total"], "210.0")
        self.assertEqual(details[1]["prompt_tokens"], "")
        self.assertEqual(details[1]["http_status"], "429")

    def test_complete_pairs_and_coverage(self):
        summary, _ = self.generate([
            {"task": 0, "mode": "pie", "model": "qd/qfmodel", "ok": True,
             "correct": True, "prompt_tokens": 600, "search_ms": [20, 40]},
            {"task": 0, "mode": "baseline", "model": "qd/qfmodel", "ok": True,
             "correct": False, "prompt_tokens": 1000},
            {"task": 1, "mode": "pie", "model": "qd/qfmodel", "ok": True,
             "correct": False, "prompt_tokens": None, "search_ms": [80]},
            {"task": 1, "mode": "baseline", "model": "qd/qfmodel", "ok": True,
             "correct": True, "prompt_tokens": 800}])
        self.assertEqual(summary["completed_pairs"], 2)
        self.assertEqual(summary["token_covered_pairs"], 1)
        self.assertEqual(summary["token_pair_coverage_pct"], 50)
        self.assertEqual(summary["input_token_saving_pct"], 40)
        self.assertEqual(summary["paired_pie_correct"], 1)
        self.assertEqual(summary["paired_baseline_correct"], 1)
        self.assertEqual(summary["retrieval_mean_ms"], 46.667)
        self.assertEqual(summary["retrieval_p95_ms"], 76)
        self.assertTrue(summary["retrieval_mean_below_100ms"])


class GatewayResponseTests(unittest.TestCase):
    def test_reasoning_only_response_is_not_a_valid_answer(self):
        from unittest import mock
        from tools.pie_agent_9router_lab import chat

        class FakeResponse:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def read(self, *_):
                return json.dumps({
                    "choices": [{
                        "message": {"role": "assistant", "content": "",
                                    "reasoning_content": "internal reasoning"},
                        "finish_reason": "length"
                    }],
                    "usage": {"prompt_tokens": 90, "completion_tokens": 1200}
                }).encode("utf8")

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            answer, usage, _, diagnostics = chat(
                [{"role": "user", "content": "test"}], "qd/qfmodel",
                "https://gateway.example", "dummy")
        self.assertEqual(answer["action"], "invalid")
        self.assertEqual(usage["prompt_tokens"], 90)
        self.assertEqual(diagnostics["content_chars"], 0)
        self.assertEqual(diagnostics["reasoning_chars"], len("internal reasoning"))
        self.assertEqual(diagnostics["finish_reason"], "length")

    def test_json_answer_remains_parseable(self):
        from unittest import mock
        from tools.pie_agent_9router_lab import chat

        class FakeResponse:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def read(self, *_):
                return json.dumps({
                    "choices": [{
                        "message": {"role": "assistant",
                                    "content": '{"action":"answer","path":"rich/text.py","symbol":"Text.copy"}'},
                        "finish_reason": "stop"
                    }],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 30}
                }).encode("utf8")

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            answer, _, _, diagnostics = chat(
                [{"role": "user", "content": "test"}], "qd/qfmodel",
                "https://gateway.example", "dummy")
        self.assertEqual(answer["action"], "answer")
        self.assertEqual(answer["symbol"], "Text.copy")
        self.assertEqual(diagnostics["parsed_action"], "answer")

if __name__ == "__main__":
    unittest.main()
