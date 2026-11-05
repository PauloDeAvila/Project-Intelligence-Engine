"""Paired OpenCode configs must differ only in PIE MCP registration."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from create_opencode_pair_configs import pair


class BenchmarkConfigTests(unittest.TestCase):
    def test_identical_permissions_and_single_treatment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            python = root / "python.exe"
            python.write_text("fixture")
            treatment, control = pair(root, python)
            self.assertEqual(treatment["permissions"], control["permissions"])
            self.assertEqual(set(treatment["mcp"]["servers"]), {"pie"})
            self.assertEqual(control["mcp"]["servers"], {})
            self.assertEqual(treatment["mcp"]["servers"]["pie"]["command"][-1],
                             str(root))
            self.assertIn(
                {"action": "shell", "resource": "*", "effect": "deny"},
                control["permissions"],
            )


if __name__ == "__main__":
    unittest.main()
