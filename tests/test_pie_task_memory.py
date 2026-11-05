"""Stage 1: task-memory persistence, safety and CLI/MCP contracts."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pie.interfaces.cli import main
from pie.interfaces.mcp_server import dispatch, TOOLS
from pie.retrieval.task_memory import start_task, record_task, resume_task
from pie.storage.database import connect


class TaskMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        c = connect(self.root / ".pie" / "index.sqlite3")
        c.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_persists_after_reopening_and_retains_event_order(self):
        started = start_task(self.root, "Repair login safely")
        identifier = started["task_id"]
        record_task(self.root, identifier, "decision", "Preserve auth API", "src/auth.py:12")
        record_task(self.root, identifier, "checkpoint", "Tests pending")
        resumed = resume_task(self.root)
        self.assertEqual(resumed["task"]["task_id"], identifier)
        self.assertEqual([e["kind"] for e in resumed["events"]], ["decision", "checkpoint"])
        self.assertEqual(resumed["events"][0]["reference"], "src/auth.py:12")
        self.assertEqual(resume_task(self.root, identifier)["task"]["objective"], "Repair login safely")

    def test_completed_excluded_from_latest_and_immutable(self):
        first = start_task(self.root, "First")["task_id"]
        record_task(self.root, first, "result", "Done", status="completed")
        self.assertEqual(resume_task(self.root)["state"], "NOT_FOUND")
        self.assertEqual(resume_task(self.root, first)["task"]["status"], "completed")
        with self.assertRaisesRegex(ValueError, "immutable"):
            record_task(self.root, first, "note", "tamper")
        self.assertEqual(len(resume_task(self.root, first)["events"]), 1)

    def test_blocked_task_can_resume_and_continue(self):
        task = start_task(self.root, "Investigate")["task_id"]
        record_task(self.root, task, "checkpoint", "Waiting for tests", status="blocked")
        self.assertEqual(resume_task(self.root)["task"]["status"], "blocked")
        record_task(self.root, task, "action", "Resumed", status="in_progress")
        self.assertEqual(resume_task(self.root)["task"]["status"], "in_progress")

    def test_project_isolation(self):
        a = start_task(self.root, "Private project task")["task_id"]
        with tempfile.TemporaryDirectory() as other:
            second = Path(other)
            connection = connect(second / ".pie" / "index.sqlite3")
            connection.close()
            self.assertEqual(resume_task(second, a)["state"], "NOT_FOUND")
            with self.assertRaisesRegex(ValueError, "Unknown"):
                record_task(second, a, "note", "Invalid cross-project write")

    def test_no_index_and_input_validation(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaisesRegex(ValueError, "init/index"):
                start_task(Path(empty), "No index")
        for objective in ("", " ", "\x00", "x" * 2049):
            with self.assertRaises(ValueError):
                start_task(self.root, objective)
        task = start_task(self.root, "Valid")["task_id"]
        for kind in ("", "unknown", "action\x00"):
            with self.assertRaises(ValueError):
                record_task(self.root, task, kind, "payload")
        with self.assertRaises(ValueError):
            record_task(self.root, task, "note", "x" * 4097)
        with self.assertRaises(ValueError):
            record_task(self.root, task, "note", "x", status="invented")
        with self.assertRaises(ValueError):
            record_task(self.root, task, "note", "x", reference="../" * 500)
        with self.assertRaises(ValueError):
            record_task(self.root, "bad", "note", "x")
        with self.assertRaises(ValueError):
            resume_task(self.root, limit=True)
        self.assertEqual(resume_task(self.root, task)["events"], [])

    def test_bounded_history_and_unicode(self):
        task = start_task(self.root, "Corrigir autenticação")["task_id"]
        for n in range(35):
            record_task(self.root, task, "action", f"Passo número {n}")
        data = resume_task(self.root, task, limit=3)
        self.assertEqual(data["omitted_events"], 32)
        self.assertEqual([e["text"] for e in data["events"]],
                         ["Passo número 32", "Passo número 33", "Passo número 34"])

    def test_cli_end_to_end(self):
        def run(*args):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main([*args, "--root", str(self.root)]), 0)
            return json.loads(output.getvalue())
        task = run("task-start", "--objective", "CLI interrupted task")["task_id"]
        run("task-record", "--task-id", task, "--kind", "checkpoint",
            "--text", "Wait for CI", "--status", "blocked")
        result = run("task-resume", "--task-id", task)
        self.assertEqual(result["task"]["status"], "blocked")
        self.assertEqual(result["events"][0]["text"], "Wait for CI")

    def test_mcp_end_to_end_and_arguments_rejected(self):
        names = {t["name"] for t in TOOLS}
        self.assertTrue({"pie_task_start", "pie_task_record", "pie_task_resume"} <= names)
        def invoke(name, args):
            reply = dispatch({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                              "params": {"name": name, "arguments": args}}, self.root)
            return reply["result"]
        result = invoke("pie_task_start", {"objective": "MCP task"})
        task = json.loads(result["content"][0]["text"])["task_id"]
        record = invoke("pie_task_record", {"task_id": task, "kind": "decision",
                          "text": "Keep rollback", "reference": "docs/decisions.md"})
        self.assertFalse(record.get("isError", False))
        summary = json.loads(invoke("pie_task_resume", {"task_id": task})["content"][0]["text"])
        self.assertEqual(summary["events"][0]["kind"], "decision")
        self.assertTrue(invoke("pie_task_resume", {"limit": 101})["isError"])
        self.assertTrue(invoke("pie_task_start", {"objective": "x", "unexpected": True})["isError"])


if __name__ == "__main__":
    unittest.main()
