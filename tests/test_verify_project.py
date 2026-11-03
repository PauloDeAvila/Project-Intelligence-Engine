import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_project", ROOT / "tools" / "verify_project.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def matrix(command=None):
    return {"checks": {tier: {"status": "not-applicable", "reason": "outside test scope"} for tier in module.TIERS}}

class ConfigurationTests(unittest.TestCase):
    def test_rejects_missing_tier(self):
        with self.assertRaisesRegex(ValueError, "Missing verification tier"):
            module.validate_config({"checks": {"unit": {"status": "required", "command": [sys.executable, "-V"]}}})

    def test_rejects_unconfigured_tier(self):
        config = matrix()
        config["checks"]["e2e"] = {"status": "unconfigured"}
        with self.assertRaisesRegex(ValueError, "e2e"):
            module.validate_config(config)

    def test_rejects_empty_command(self):
        config = matrix()
        config["checks"]["unit"] = {"status": "required", "command": []}
        with self.assertRaisesRegex(ValueError, "command"):
            module.validate_config(config)

    def test_requires_reason_for_skipped_tier(self):
        config = matrix()
        config["checks"]["e2e"]["reason"] = ""
        with self.assertRaisesRegex(ValueError, "reason"):
            module.validate_config(config)

    def test_accepts_explicit_non_applicable(self):
        module.validate_config(matrix())

    def test_real_command_passes_and_records_evidence(self):
        config = matrix()
        config["checks"]["unit"] = {"status": "required", "command": [sys.executable, "-c", "raise SystemExit(0)"]}
        with tempfile.TemporaryDirectory() as d, patch.object(module, "ROOT", pathlib.Path(d)):
            self.assertEqual(module.run(config), 0)
            results = json.loads((pathlib.Path(d) / "verification-results.json").read_text())["results"]
            self.assertEqual(results[0]["status"], "passed")
            self.assertEqual(results[0]["returncode"], 0)

    def test_failed_command_blocks_delivery_and_records_evidence(self):
        config = matrix()
        config["checks"]["unit"] = {"status": "required", "command": [sys.executable, "-c", "import sys; print('failure context'); print('failure details', file=sys.stderr); raise SystemExit(7)"]}
        with tempfile.TemporaryDirectory() as d, patch.object(module, "ROOT", pathlib.Path(d)):
            self.assertEqual(module.run(config), 1)
            results = json.loads((pathlib.Path(d) / "verification-results.json").read_text())["results"]
            self.assertEqual(results[0]["status"], "failed")
            self.assertEqual(results[0]["returncode"], 7)
            self.assertIn("failure context", results[0]["stdout"]["text"])
            self.assertIn("failure details", results[0]["stderr"]["text"])

    def test_failed_output_is_bounded_redacted_and_unicode_safe(self):
        config = matrix()
        config["checks"]["unit"] = {"status": "required", "command": [sys.executable, "-c", "import os, sys; print('x' * 20000); print(os.environ['PIE_TEST_TOKEN']); print('password=hunter22'); print('Bearer abc.def.ghi'); sys.stdout.buffer.write(b'\\xff'); raise SystemExit(7)"]}
        with tempfile.TemporaryDirectory() as d, patch.object(module, "ROOT", pathlib.Path(d)), patch.dict(os.environ, {"PIE_TEST_TOKEN": "private-test-credential-719"}), redirect_stdout(io.StringIO()):
            self.assertEqual(module.run(config), 1)
            raw = (pathlib.Path(d) / "verification-results.json").read_text(encoding="utf-8")
            row = json.loads(raw)["results"][0]
            self.assertTrue(row["stdout"]["truncated"])
            self.assertLessEqual(len(row["stdout"]["text"].encode("utf-8")), module.OUTPUT_LIMIT)
            for secret in ("private-test-credential-719", "hunter22", "abc.def.ghi"):
                self.assertNotIn(secret, raw)
            self.assertIn("[REDACTED]", raw)

    def test_timeout_records_partial_diagnostic_output(self):
        config = matrix()
        config["checks"]["unit"] = {"status": "required", "timeout_seconds": 0.2, "command": [sys.executable, "-u", "-c", "import time; print('before timeout', flush=True); time.sleep(10)"]}
        with tempfile.TemporaryDirectory() as d, patch.object(module, "ROOT", pathlib.Path(d)), redirect_stdout(io.StringIO()):
            self.assertEqual(module.run(config), 1)
            row = json.loads((pathlib.Path(d) / "verification-results.json").read_text())["results"][0]
            self.assertEqual(row["status"], "blocked")
            self.assertIn("before timeout", row["stdout"]["text"])

    def test_missing_executable_blocks_delivery(self):
        config = matrix()
        config["checks"]["unit"] = {"status": "required", "command": ["nonexistent_verify_project_executable_539193"]}
        with tempfile.TemporaryDirectory() as d, patch.object(module, "ROOT", pathlib.Path(d)):
            self.assertEqual(module.run(config), 1)
            results = json.loads((pathlib.Path(d) / "verification-results.json").read_text())["results"]
            self.assertEqual(results[0]["status"], "blocked")

    def test_project_configuration_is_fully_configured(self):
        config = json.loads((ROOT / "ci" / "checks.json").read_text(encoding="utf-8"))
        module.validate_config(config)

if __name__ == "__main__":
    unittest.main()
