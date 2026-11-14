"""Task telemetry regression tests: no invented provider tokens."""
from __future__ import annotations
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pie.certification.task_telemetry import app_for, record_task, import_provider_record, report


class TaskTelemetryTests(unittest.TestCase):
    def test_domain_classification(self):
        self.assertEqual(app_for("mcp", "browser_snapshot"), "web")
        self.assertEqual(app_for("mcp", "get_scene_info"), "blender")
        self.assertEqual(app_for("terminal", "git status"), "terminal")

    def test_task_is_recorded_without_fabricated_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {"PIE_TASK_ID": "material-roughness", "PIE_APP": "blender"}):
                record_task(root, surface="mcp", tool="get_scene_info",
                            state="PARTIAL", source_chars=2000,
                            returned_chars=500, elapsed_ms=8.5)
            data = report(root)
            self.assertEqual(data["state"], "OBSERVED")
            self.assertEqual(len(data["apps"]), 1)
            row = data["apps"][0]
            self.assertEqual(row["task_id"], "material-roughness")
            self.assertEqual(row["app"], "blender")
            self.assertEqual(row["saved_chars"], 1500)
            self.assertIsNone(row["input_tokens"])
            self.assertFalse(data["provider_certified"])

    def test_invalid_task_id_falls_back_to_unassigned(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"PIE_TASK_ID": "unsafe / name"}):
                record_task(Path(tmp), surface="mcp", tool="browser_snapshot",
                            state="PASS", source_chars=10,
                            returned_chars=10, elapsed_ms=1.0)
            self.assertEqual(report(Path(tmp))["apps"][0]["task_id"], "unassigned")

    def test_run_and_condition_are_automatic_and_queryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"PIE_TASK_ID": "scene-read",
                                          "PIE_RUN_ID": "run-07",
                                          "PIE_CONDITION": "optimized"}):
                record_task(Path(tmp), surface="mcp", tool="browser_snapshot",
                            state="SUCCESS", source_chars=100,
                            returned_chars=40, elapsed_ms=12.25)
            row = report(Path(tmp))["apps"][0]
            self.assertEqual(row["run_id"], "run-07")
            self.assertEqual(row["condition"], "optimized")
            self.assertEqual(row["elapsed_ms"], 12.25)

    def test_provider_import_is_idempotent_and_keeps_real_usage(self):
        record = {
            "schema": "pie-live-codex-usage-v1", "provider_reported": True,
            "source": "codex_exec_json_turn_completed", "condition": "optimized",
            "scenario_id": "scene-read", "repetition": 2, "model": "m",
            "codex_version": "c", "prompt_sha256": "p", "expected_sha256": "e",
            "workspace_commit": "w", "configuration_sha256": "cfg",
            "oracle_kind": "exact_text", "oracle_pass": True, "tool_events": 1,
            "runtime_ms": 12.5, "usage": {"input_tokens": 100,
                "cached_input_tokens": 40, "output_tokens": 7}
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            import_provider_record(root, record, app="blender", task_id="scene-read")
            import_provider_record(root, record, app="blender", task_id="scene-read")
            data = report(root)
            self.assertEqual(len(data["apps"]), 1)
            self.assertEqual(data["apps"][0]["events"], 1)
            self.assertEqual(data["apps"][0]["input_tokens"], 100)


if __name__ == "__main__":
    unittest.main()
