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

    def test_optimized_exposed_tools_are_opt_in(self):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is unavailable")
        with tempfile.TemporaryDirectory(prefix="pie-phase3-profile-expose-test-") as tmp:
            output = Path(tmp)
            command = [powershell, "-NoProfile", "-File",
                       str(ROOT / "tools" / "prepare_phase3_profiles.ps1"),
                       "-Workspace", str(ROOT), "-OutputDirectory", str(output),
                       "-OptimizedExposeTool", "get_scene_info"]
            result = subprocess.run(command, cwd=ROOT, text=True,
                                    capture_output=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            optimized = tomllib.loads(
                (output / "pie-phase3-optimized.config.toml").read_text(encoding="utf-8")
            )
            args = optimized["mcp_servers"]["pie-blender-optimized"]["args"]
            self.assertIn("--expose-tool", args)
            self.assertIn("get_scene_info", args)

    def test_selective_query_profile_exposes_only_the_opt_in_tool(self):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is unavailable")
        with tempfile.TemporaryDirectory(prefix="pie-phase3-query-profile-test-") as tmp:
            output = Path(tmp)
            command = [powershell, "-NoProfile", "-File",
                       str(ROOT / "tools" / "prepare_phase3_profiles.ps1"),
                       "-Workspace", str(ROOT), "-OutputDirectory", str(output),
                       "-Domain", "blender", "-BaselineExposeTool", "get_scene_info",
                       "-OptimizedExposeTool", "pie_blender_query_scene",
                       "-PieCommit", "0" * 40]
            result = subprocess.run(command, cwd=ROOT, text=True,
                                    capture_output=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            baseline = tomllib.loads((output / "pie-phase3-baseline.config.toml").read_text(encoding="utf-8"))
            optimized = tomllib.loads((output / "pie-phase3-optimized.config.toml").read_text(encoding="utf-8"))
            self.assertNotIn("enabled_tools", baseline)
            self.assertNotIn("enabled_tools", optimized)
            self.assertEqual(baseline["mcp_servers"]["blender"]["enabled_tools"], ["get_scene_info"])
            self.assertEqual(optimized["mcp_servers"]["pie-blender-optimized"]["enabled_tools"], ["pie_blender_query_scene"])
            self.assertEqual(set(baseline["mcp_servers"]["blender"]["tools"]), {"get_scene_info"})
            self.assertEqual(set(optimized["mcp_servers"]["pie-blender-optimized"]["tools"]),
                             {"pie_blender_query_scene"})
            self.assertIn("pie_blender_query_scene", optimized["mcp_servers"]["pie-blender-optimized"]["args"])
            self.assertIn("pie_blender_query_scene", optimized["mcp_servers"]["pie-blender-optimized"]["tools"])

    def test_profiles_can_disable_inherited_servers(self):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell is unavailable")
        with tempfile.TemporaryDirectory(prefix="pie-phase3-profile-isolation-test-") as tmp:
            output = Path(tmp)
            command = [powershell, "-NoProfile", "-File",
                       str(ROOT / "tools" / "prepare_phase3_profiles.ps1"),
                       "-Workspace", str(ROOT), "-OutputDirectory", str(output),
                       "-Domain", "blender", "-BaselineDisableServer", "pie-blender-optimized",
                       "-OptimizedDisableServer", "blender",
                       "-PieCommit", "0" * 40]
            result = subprocess.run(command, cwd=ROOT, text=True,
                                    capture_output=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            baseline = tomllib.loads((output / "pie-phase3-baseline.config.toml").read_text(encoding="utf-8"))
            optimized = tomllib.loads((output / "pie-phase3-optimized.config.toml").read_text(encoding="utf-8"))
            self.assertFalse(baseline["mcp_servers"]["pie-blender-optimized"]["enabled"])
            self.assertFalse(optimized["mcp_servers"]["blender"]["enabled"])


if __name__ == "__main__":
    unittest.main()
