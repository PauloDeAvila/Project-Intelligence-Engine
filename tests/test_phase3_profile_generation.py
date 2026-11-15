"""Offline contract for the isolated Phase 3 Codex profile generator."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Phase3ProfileGenerationTests(unittest.TestCase):
    def test_baseline_and_optimized_names_match_controller_routes(self):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is unavailable")
        with tempfile.TemporaryDirectory(prefix="pie-phase3-profile-test-") as tmp:
            output = Path(tmp)
            command = [
                powershell,
                "-NoProfile",
                "-File",
                str(ROOT / "tools" / "prepare_phase3_profiles.ps1"),
                "-Workspace",
                str(ROOT),
                "-OutputDirectory",
                str(output),
            ]
            result = subprocess.run(command, cwd=ROOT, text=True,
                                    capture_output=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            baseline = tomllib.loads(
                (output / "pie-phase3-baseline.config.toml").read_text(encoding="utf-8")
            )
            optimized = tomllib.loads(
                (output / "pie-phase3-optimized.config.toml").read_text(encoding="utf-8")
            )
            self.assertEqual(set(baseline["mcp_servers"]),
                             {"blender", "playwright-baseline"})
            self.assertEqual(set(optimized["mcp_servers"]),
                             {"pie-blender-optimized", "pie-web-optimized"})
            self.assertNotIn("pie.gateway.domain", baseline["mcp_servers"]["blender"]["args"])
            self.assertIn("pie.gateway.domain",
                          optimized["mcp_servers"]["pie-blender-optimized"]["args"])


if __name__ == "__main__":
    unittest.main()
