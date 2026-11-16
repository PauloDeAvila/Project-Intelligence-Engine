import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_context_runtime import verify


def _entry(mode, prompt, completion, total, successful=5, correct=5,
           host="localhost", scheme="http", cached=None, uncached=None):
    entry = {
        "host": host,
        "scheme": scheme,
        "model": "pilot-model",
        "mode": mode,
        "calls": successful,
        "successful": successful,
        "exact_correct": correct,
        "evidence_hit": successful,
        "provider_usage_status": "ok",
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "median_latency_s": 1.0,
    }
    if cached is not None:
        entry["cached_input_tokens"] = cached
    if uncached is not None:
        entry["uncached_input_tokens"] = uncached
    return entry


def _summary(baseline, pie):
    return {"results": [baseline, pie], "index_seconds": 0.0,
            "qualification": "pilot"}


class ContextRuntimeVerifierTests(unittest.TestCase):
    def test_default_mode_is_uncertified_and_unavailable(self):
        result = verify()
        self.assertEqual(result["schema"], "pie-context-runtime-verifier-v1")
        self.assertEqual(result["status"], "PASS_LOCAL")
        self.assertTrue(result["local_validation"])
        self.assertEqual(result["certification"], "NOT_CERTIFIED")
        self.assertEqual(result["external_provider_usage"], "unavailable")
        self.assertEqual(
            result["note"],
            "Synthetic evaluator evidence is not external provider usage.",
        )
        self.assertNotIn("external_evidence_status", result)

    def _write(self, directory, payload):
        path = Path(directory) / "summary.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_valid_single_pair_evidence_is_pilot_valid_but_not_certified(self):
        baseline = _entry("baseline", 1000, 100, 1100)
        pie = _entry("pie", 700, 100, 800)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "PASS_LOCAL")
        self.assertEqual(result["certification"], "NOT_CERTIFIED")
        usage = result["external_provider_usage"]
        self.assertEqual(usage["external_evidence_status"], "PILOT_VALID")
        self.assertEqual(usage["model"], "pilot-model")
        self.assertEqual(usage["pair_count"], 5)
        self.assertEqual(usage["correct_pairs"], 5)
        self.assertEqual(usage["baseline_tokens"], 1100)
        self.assertEqual(usage["pie_tokens"], 800)
        self.assertEqual(usage["input_savings_percent"], 30.0)
        self.assertEqual(usage["total_savings_percent"],
                         round(100 * 300 / 1100, 3))
        self.assertIsNone(usage["baseline_cached_input_tokens"])
        self.assertIsNone(usage["baseline_uncached_input_tokens"])
        self.assertIsNone(usage["pie_cached_input_tokens"])
        self.assertIsNone(usage["pie_uncached_input_tokens"])

    def test_cache_present_on_both_entries_is_exposed(self):
        baseline = _entry("baseline", 1000, 100, 1100, cached=400, uncached=600)
        pie = _entry("pie", 700, 100, 800, cached=300, uncached=400)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "PASS_LOCAL")
        usage = result["external_provider_usage"]
        self.assertEqual(usage["external_evidence_status"], "PILOT_VALID")
        self.assertEqual(usage["input_savings_percent"], 30.0)
        self.assertEqual(usage["total_savings_percent"],
                         round(100 * 300 / 1100, 3))
        self.assertEqual(usage["baseline_cached_input_tokens"], 400)
        self.assertEqual(usage["baseline_uncached_input_tokens"], 600)
        self.assertEqual(usage["pie_cached_input_tokens"], 300)
        self.assertEqual(usage["pie_uncached_input_tokens"], 400)

    def test_insufficient_sample_keeps_not_certified(self):
        baseline = _entry("baseline", 500, 50, 550, successful=2, correct=2)
        pie = _entry("pie", 400, 50, 450, successful=2, correct=2)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "PASS_LOCAL")
        self.assertEqual(result["certification"], "NOT_CERTIFIED")
        self.assertEqual(
            result["external_provider_usage"]["external_evidence_status"],
            "PILOT_VALID",
        )
        self.assertEqual(result["external_provider_usage"]["pair_count"], 2)
        self.assertIn("certification_note", result)

    def test_missing_usage_is_rejected_fail_closed(self):
        baseline = _entry("baseline", 500, 50, 550)
        baseline["provider_usage_status"] = "missing"
        pie = _entry("pie", 400, 50, 450)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "FAIL_LOCAL")
        self.assertFalse(result["local_validation"])
        self.assertEqual(result["certification"], "NOT_CERTIFIED")
        self.assertEqual(result["external_evidence_status"], "INVALID")
        self.assertEqual(result["external_provider_usage"], "unavailable")
        self.assertIn("provider_usage_status", result["failure_reason"])

    def test_invalid_path_is_rejected_fail_closed(self):
        result = verify(Path("does-not-exist.json"))
        self.assertEqual(result["status"], "FAIL_LOCAL")
        self.assertEqual(result["external_evidence_status"], "INVALID")

    def test_invented_token_types_are_rejected(self):
        baseline = _entry("baseline", True, 50, 550)
        pie = _entry("pie", 400, 50, 450)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "FAIL_LOCAL")
        self.assertEqual(result["external_evidence_status"], "INVALID")

    def test_remote_https_evidence_is_accepted(self):
        baseline = _entry("baseline", 1000, 100, 1100,
                          host="gateway.example.com", scheme="https")
        pie = _entry("pie", 700, 100, 800,
                     host="gateway.example.com", scheme="https")
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "PASS_LOCAL")
        usage = result["external_provider_usage"]
        self.assertEqual(usage["external_evidence_status"], "PILOT_VALID")
        self.assertEqual(usage["host"], "gateway.example.com")
        self.assertEqual(usage["scheme"], "https")

    def test_remote_http_evidence_is_rejected_fail_closed(self):
        baseline = _entry("baseline", 1000, 100, 1100,
                          host="gateway.example.com", scheme="http")
        pie = _entry("pie", 700, 100, 800,
                     host="gateway.example.com", scheme="http")
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "FAIL_LOCAL")
        self.assertFalse(result["local_validation"])
        self.assertEqual(result["external_evidence_status"], "INVALID")
        self.assertEqual(result["external_provider_usage"], "unavailable")
        self.assertIn("HTTP", result["failure_reason"])

    def test_loopback_http_evidence_is_accepted(self):
        baseline = _entry("baseline", 1000, 100, 1100,
                          host="127.0.0.1", scheme="http")
        pie = _entry("pie", 700, 100, 800,
                     host="127.0.0.1", scheme="http")
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "PASS_LOCAL")
        usage = result["external_provider_usage"]
        self.assertEqual(usage["external_evidence_status"], "PILOT_VALID")
        self.assertEqual(usage["host"], "127.0.0.1")
        self.assertEqual(usage["scheme"], "http")

    def test_missing_scheme_for_remote_host_is_rejected(self):
        baseline = _entry("baseline", 1000, 100, 1100,
                          host="gateway.example.com")
        baseline["scheme"] = None
        pie = _entry("pie", 700, 100, 800, host="gateway.example.com")
        pie["scheme"] = None
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "FAIL_LOCAL")
        self.assertEqual(result["external_evidence_status"], "INVALID")

    def test_mixed_schemes_are_rejected(self):
        baseline = _entry("baseline", 1000, 100, 1100,
                          host="gateway.example.com", scheme="https")
        pie = _entry("pie", 700, 100, 800,
                     host="gateway.example.com", scheme="http")
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "FAIL_LOCAL")
        self.assertEqual(result["external_evidence_status"], "INVALID")

    def test_incoherent_cached_tokens_are_rejected_fail_closed(self):
        baseline = _entry("baseline", 1000, 100, 1100, cached=1101, uncached=0)
        pie = _entry("pie", 700, 100, 800, cached=300, uncached=400)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "FAIL_LOCAL")
        self.assertFalse(result["local_validation"])
        self.assertEqual(result["certification"], "NOT_CERTIFIED")
        self.assertEqual(result["external_evidence_status"], "INVALID")
        self.assertEqual(result["external_provider_usage"], "unavailable")
        self.assertIn("cached_input_tokens", result["failure_reason"])

    def test_cached_plus_uncached_not_equal_prompt_is_rejected_fail_closed(self):
        baseline = _entry("baseline", 1000, 100, 1100, cached=400, uncached=500)
        pie = _entry("pie", 700, 100, 800, cached=300, uncached=400)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "FAIL_LOCAL")
        self.assertFalse(result["local_validation"])
        self.assertEqual(result["certification"], "NOT_CERTIFIED")
        self.assertEqual(result["external_evidence_status"], "INVALID")
        self.assertEqual(result["external_provider_usage"], "unavailable")
        self.assertIn("prompt_tokens", result["failure_reason"])

    def test_negative_cached_tokens_are_rejected_fail_closed(self):
        baseline = _entry("baseline", 1000, 100, 1100, cached=-1, uncached=1001)
        pie = _entry("pie", 700, 100, 800, cached=300, uncached=400)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "FAIL_LOCAL")
        self.assertFalse(result["local_validation"])
        self.assertEqual(result["external_evidence_status"], "INVALID")
        self.assertEqual(result["external_provider_usage"], "unavailable")
        self.assertIn("cached_input_tokens", result["failure_reason"])

    def test_non_integer_uncached_tokens_are_rejected_fail_closed(self):
        baseline = _entry("baseline", 1000, 100, 1100, cached=400, uncached="600")
        pie = _entry("pie", 700, 100, 800, cached=300, uncached=400)
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, _summary(baseline, pie))
            result = verify(path)
        self.assertEqual(result["status"], "FAIL_LOCAL")
        self.assertEqual(result["external_evidence_status"], "INVALID")
        self.assertIn("uncached_input_tokens", result["failure_reason"])


if __name__ == "__main__":
    unittest.main()
