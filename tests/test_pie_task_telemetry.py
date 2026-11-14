"""Task telemetry regression tests: no invented provider tokens."""
from __future__ import annotations
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pie.certification.task_telemetry import app_for, record_task, report


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


if __name__ == "__main__":
    unittest.main()
