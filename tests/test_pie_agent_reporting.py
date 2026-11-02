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

    def test_preflight_failure_keeps_missing_metrics_null(self):
        summary, details = self.generate([])
        self.assertEqual(summary["attempts"], 0)
        self.assertEqual(summary["completed_pairs"], 0)
        self.assertEqual(summary["pie_no_search_attempts"], 0)
        self.assertIsNone(summary["input_token_saving_pct"])
        self.assertIsNone(summary["retrieval_mean_ms"])
        self.assertIsNone(summary["retrieval_p95_ms"])
        self.assertEqual(summary["http_successes_measured"], 0)
        self.assertFalse(summary["certification"]["fully_certified"])

    def test_failed_pie_request_is_not_counted_as_no_search(self):
        summary, _ = self.generate([
            {"task": 0, "mode": "pie", "model": "qd/qfmodel",
             "ok": False, "error": "URLError", "http_status": None},
            {"task": 0, "mode": "baseline", "model": "qd/qfmodel",
             "ok": False, "error": "URLError", "http_status": None},
        ])
        self.assertEqual(summary["pie_no_search_attempts"], 0)
        self.assertEqual(summary["http_failures"], 0)
        self.assertEqual(summary["http_status_covered_attempts"], 0)


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
        self.assertEqual(summary["token_question_coverage_pct"], 3.33)
        self.assertEqual(summary["completed_question_coverage_pct"], 6.67)
        self.assertEqual(summary["input_token_saving_pct"], 40)
        self.assertEqual(summary["paired_pie_correct"], 1)
        self.assertEqual(summary["paired_baseline_correct"], 1)
        self.assertEqual(summary["retrieval_mean_ms"], 46.667)
        self.assertEqual(summary["retrieval_p95_ms"], 76)
        self.assertTrue(summary["retrieval_mean_below_100ms"])



    def test_invalid_agent_output_is_reported_without_fabricating_http_status(self):
        summary, details = self.generate([
            {"task": 0, "mode": "pie", "model": "qd/qfmodel", "ok": True,
             "correct": False, "answer": {}, "answer_valid": False,
             "calls": 1, "searches": 0, "prompt_tokens": 90,
             "response_diagnostics": [{
                 "http_status": 200, "finish_reason": "length",
                 "content_chars": 0, "reasoning_chars": 1200,
                 "parsed_action": "invalid"
             }]},
            {"task": 0, "mode": "baseline", "model": "qd/qfmodel", "ok": True,
             "correct": False, "answer": {}, "answer_valid": False,
             "calls": 1, "searches": 0, "prompt_tokens": 1000}
        ])
        self.assertEqual(summary["completed_pairs"], 1)
        self.assertEqual(summary["valid_answer_pairs"], 0)
        self.assertEqual(summary["invalid_answer_attempts"], 2)
        self.assertEqual(summary["pie_no_search_attempts"], 1)
        self.assertEqual(summary["http_successes_measured"], 1)
        self.assertEqual(summary["http_status_covered_attempts"], 1)
        self.assertEqual(details[0]["last_finish_reason"], "length")
        self.assertEqual(details[0]["last_content_chars"], "0")
        self.assertEqual(details[1]["http_successes_measured"], "")


class AgentPairingTests(unittest.TestCase):
    def test_agent_summary_pairs_distinct_task_ids_without_generator_capture(self):
        from tools.pie_agent_9router_lab import summarize_model_results
        rows = [
            {"model": "qd/qfmodel", "task": 0, "mode": "baseline",
             "ok": False, "correct": None, "prompt_tokens": None},
            {"model": "qd/qfmodel", "task": 0, "mode": "pie",
             "ok": True, "correct": True, "prompt_tokens": 100},
            {"model": "qd/qfmodel", "task": 1, "mode": "baseline",
             "ok": True, "correct": True, "prompt_tokens": 400},
            {"model": "qd/qfmodel", "task": 1, "mode": "pie",
             "ok": True, "correct": False, "prompt_tokens": 200},
        ]
        result = summarize_model_results(rows, ["qd/qfmodel"], 2)[0]
        self.assertEqual(result["completed_pairs"], 1)
        self.assertEqual(result["token_covered_pairs"], 1)
        self.assertEqual(result["baseline_correct"], 1)
        self.assertEqual(result["pie_correct"], 0)
        self.assertEqual(result["baseline_prompt_tokens"], 400)
        self.assertEqual(result["pie_prompt_tokens"], 200)
        self.assertEqual(result["token_saving_pct"], 50)


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

    def test_gateway_preflight_reports_transport_category_without_endpoint(self):
        from unittest import mock
        from urllib.error import URLError, HTTPError
        from tools.pie_agent_9router_lab import probe_gateway
        with mock.patch("tools.pie_agent_9router_lab.chat",
                        side_effect=URLError(OSError("Name or service not known"))):
            outcome = probe_gateway("https://private-gateway.example", "secret-token", "qd/qfmodel")
        self.assertFalse(outcome["ok"])
        self.assertEqual(outcome["category"], "dns_resolution_failed")
        self.assertIsNone(outcome["http_status"])
        self.assertNotIn("secret-token", json.dumps(outcome))
        with mock.patch("tools.pie_agent_9router_lab.chat",
                        side_effect=HTTPError("https://private-gateway.example", 401,
                                              "Unauthorized", {}, None)):
            rejected = probe_gateway("https://private-gateway.example", "secret-token", "qd/qfmodel")
        self.assertEqual(rejected["http_status"], 401)
        self.assertEqual(rejected["category"], "http_error")

    def test_gateway_preflight_success_does_not_require_valid_agent_answer(self):
        from unittest import mock
        from tools.pie_agent_9router_lab import probe_gateway
        with mock.patch("tools.pie_agent_9router_lab.chat",
                        return_value=({"action":"invalid"}, {}, 0.01, {"http_status":200})):
            outcome = probe_gateway("https://gateway.example", "key", "qd/qfmodel")
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["http_status"], 200)


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
