import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class CliWorkflowTests(unittest.TestCase):
    def run_cli(self, root, *args):
        environment = dict(__import__("os").environ, PYTHONPATH=str(ROOT / "src"))
        return subprocess.run([sys.executable, "-m", "pie", *args, "--root", str(root)], cwd=ROOT, env=environment, capture_output=True, text=True, check=False)

    def test_init_index_status_and_search_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "main.py").write_text("class App:\n    def run(self):\n        pass\n", encoding="utf-8")
            self.assertEqual(self.run_cli(root, "init").returncode, 0)
            indexed = self.run_cli(root, "index")
            self.assertEqual(indexed.returncode, 0, indexed.stderr)
            self.assertEqual(json.loads(indexed.stdout)["symbols"], 2)
            status = self.run_cli(root, "status")
            self.assertEqual(json.loads(status.stdout)["files"], 1)
            search = self.run_cli(root, "search", "App")
            self.assertEqual([item["qualified_name"] for item in json.loads(search.stdout)], ["App", "App.run"])

