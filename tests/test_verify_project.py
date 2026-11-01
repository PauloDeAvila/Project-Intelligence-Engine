import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
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
        config["checks"]["unit"] = {"status": "required", "command": [sys.executable, "-c", "raise SystemExit(7)"]}
        with tempfile.TemporaryDirectory() as d, patch.object(module, "ROOT", pathlib.Path(d)):
            self.assertEqual(module.run(config), 1)
            results = json.loads((pathlib.Path(d) / "verification-results.json").read_text())["results"]
            self.assertEqual(results[0]["status"], "failed")
            self.assertEqual(results[0]["returncode"], 7)

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
