"""Persistence/restart and bounded evidence-recovery regression tests."""
import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pie.storage.database import connect
from pie.retrieval.output_pipeline import compact_output, recover_output, MAX_OUTPUT_ROWS
from pie.interfaces.tool_gateway import execute_gateway


class MemoryIntegrationRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        connect(self.root / ".pie" / "index.sqlite3").close()
        self.env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args):
        completed = subprocess.run(
            [sys.executable, "-m", "pie", *args, "--root", str(self.root)],
            text=True, capture_output=True, env=self.env, timeout=20,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_task_survives_three_separate_processes(self):
        task_id = self.cli("task-start", "--objective", "Continue scene material work")["task_id"]
        self.cli("task-record", "--task-id", task_id, "--kind", "decision",
                 "--text", "Maintain original metallic node structure",
                 "--reference", "src/materials.py:15")
        again = self.cli("task-resume", "--task-id", task_id)
        self.assertEqual(again["task"]["task_id"], task_id)
        self.assertEqual(len(again["events"]), 1)
        self.assertEqual(self.cli("task-search", "metallic")["matches"][0]["task_id"], task_id)

    def test_identical_output_is_deduplicated_per_project(self):
        first = compact_output(self.root, "same diagnostic", kind="test")
        second = compact_output(self.root, "same diagnostic", kind="test")
        self.assertEqual(first["output_id"], second["output_id"])
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        with closing(sqlite3.connect(self.root / ".pie" / "index.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM pie_tool_outputs").fetchone()[0], 1)

    def test_output_retention_and_expiry(self):
        first = compact_output(self.root, "old first")["output_id"]
        with closing(sqlite3.connect(self.root / ".pie" / "index.sqlite3")) as db:
            with db:
                db.execute("UPDATE pie_tool_outputs SET created_utc='2000-01-01T00:00:00+00:00' "
                           "WHERE output_id=?", (first,))
        recent = compact_output(self.root, "recent")["output_id"]
        self.assertEqual(recover_output(self.root, recent)["text"], "recent")
        with self.assertRaisesRegex(ValueError, "Unknown output"):
            recover_output(self.root, first)

    def test_output_has_bounded_row_count(self):
        ids = [compact_output(self.root, "message " + str(n))["output_id"]
               for n in range(MAX_OUTPUT_ROWS + 4)]
        with closing(sqlite3.connect(self.root / ".pie" / "index.sqlite3")) as db:
            number = db.execute("SELECT COUNT(*) FROM pie_tool_outputs").fetchone()[0]
        self.assertLessEqual(number, MAX_OUTPUT_ROWS)
        self.assertEqual(recover_output(self.root, ids[-1])["text"], "message " + str(MAX_OUTPUT_ROWS + 3))
        with self.assertRaisesRegex(ValueError, "Unknown output"):
            recover_output(self.root, ids[0])

    def test_source_manifest_fails_closed_after_edit(self):
        original = b"def material():\n    return 0.35\n"
        source = self.root / "material.py"
        source.write_bytes(original)
        import hashlib
        manifest = [{"path": "material.py", "sha256": hashlib.sha256(original).hexdigest()}]
        record = compact_output(self.root, "material source proof", source_manifest=manifest)
        self.assertEqual(recover_output(self.root, record["output_id"])["text"], "material source proof")
        source.write_text("def material():\n    return 0.1\n", encoding="utf8")
        with self.assertRaisesRegex(ValueError, "changed or stale"):
            recover_output(self.root, record["output_id"])

    def test_gateway_context_pack_becomes_stale_on_source_edit(self):
        from pie.indexing.indexer import index_project
        target = self.root / "logic.py"
        target.write_text("def calculate(value):\n    return value + 1\n", encoding="utf8")
        indexed = index_project(self.root)
        self.assertEqual(indexed["index_state"], "CURRENT")
        delivered = execute_gateway(self.root, "context_pack", {"symbol": "calculate"},
                                    max_chars=4000)
        output_id = delivered["telemetry"]["output_id"]
        self.assertGreaterEqual(delivered["telemetry"]["verified_source_files"], 1)
        recovered = execute_gateway(self.root, "output_get", {"output_id": output_id},
                                    max_chars=64000)
        self.assertIn("calculate", recovered["result"]["text"])
        target.write_text("def calculate(value):\n    return value + 2\n", encoding="utf8")
        with self.assertRaisesRegex(ValueError, "changed or stale"):
            execute_gateway(self.root, "output_get", {"output_id": output_id},
                            max_chars=64000)

    def test_gateway_recovery_pages_without_oversized_payload(self):
        record = compact_output(self.root, "TRACE " + "x" * 12000)
        offset = 0
        chunks = []
        while True:
            response = execute_gateway(
                self.root, "output_get",
                {"output_id": record["output_id"], "start": offset}, max_chars=1200,
            )
            self.assertLessEqual(len(json.dumps(response, ensure_ascii=False, separators=(",", ":"))), 1200)
            part = response["result"]
            chunks.append(part["text"])
            offset = part["end"]
            if part["remaining_chars"] == 0:
                break
            self.assertEqual(response["state"], "PARTIAL")
        self.assertEqual("".join(chunks), "TRACE " + "x"*12000)

    def test_cross_project_recovery_isolation(self):
        record = compact_output(self.root, "limited to A")
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp)
            connect(other / ".pie" / "index.sqlite3").close()
            with self.assertRaises(ValueError):
                execute_gateway(other, "output_get", {"output_id": record["output_id"]})


if __name__ == "__main__":
    unittest.main()
