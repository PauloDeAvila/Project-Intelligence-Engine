import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from create_opencode_pie_config import make_config, main


class OpenCodePieConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "pie repo"
        self.root.mkdir()
        self.python = self.root / "python.exe"
        self.python.write_text("fixture")

    def test_root_binds_to_pie_not_doctor_mesh(self):
        config = make_config(self.root, self.python)
        mcp = config["mcp"]["servers"]
        self.assertEqual(set(mcp), {"pie"})
        self.assertEqual(mcp["pie"]["command"][-1], str(self.root.resolve()))
        self.assertEqual(mcp["pie"]["command"][1:4],
                         ["-m", "pie.interfaces.mcp_server", "--root"])
        self.assertIn({"action": "shell", "resource": "*", "effect": "deny"}, config["permissions"])

    def test_requires_real_explicit_paths(self):
        with self.assertRaises(ValueError):
            make_config(Path("relative"), self.python)
        with self.assertRaises(ValueError):
            make_config(self.root, self.root / "missing.exe")

    def test_generates_new_private_file_without_overwrite(self):
        target = self.root.parent / "private" / "opencode-pie.json"
        args = ["--root", str(self.root), "--python", str(self.python),
                "--output", str(target)]
        self.assertEqual(main(args), 0)
        data = json.loads(target.read_text("utf-8"))
        self.assertEqual(data["mcp"]["servers"]["pie"]["command"][-1], str(self.root))
        with self.assertRaises(SystemExit):
            main(args)


if __name__ == "__main__":
    unittest.main()
