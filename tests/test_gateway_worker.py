"""Gateway queue dispatch regression tests (real loopback, fake model)."""
from pathlib import Path
import json
import sys
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pie.orchestrator.gateway import Gateway
from pie.orchestrator.service import Orchestrator, ProjectPolicy, Execution
from pie.orchestrator.store import TaskStore
from pie.orchestrator.models import TaskStatus


class FakeFreshness:
    def validate(self, project):
        return {"index_state": "CURRENT", "files": 1}


class FakeAdapter:
    def __init__(self):
        self.calls = 0

    def execute(self, task, project, prompt, on_session=None):
        self.calls += 1
        if on_session:
            on_session("session_worker")
        return Execution("session_worker", {"pie_mcp_evidence": [{
            "tool": "pie_project_status", "status": "completed",
            "output_sha256": "0" * 64, "output_bytes": 7
        }]}, {"input": 3, "output": 2})

    def cancel(self, session_id):
        pass


class GatewayWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self.store = TaskStore(root / "state.sqlite3")
        self.addCleanup(self.store.close)
        self.adapter = FakeAdapter()
        self.service = Orchestrator(
            self.store, {"pie": ProjectPolicy("pie", root, frozenset({"demo/model"}))},
            self.adapter, FakeFreshness(),
        )
        self.payload = {"project_id": "pie", "task_type": "read_only_review",
                        "model": "demo/model", "idempotency_key": "issue-99"}

    def start(self, auto_execute):
        server = Gateway(("127.0.0.1", 0), self.service, "test-only", "",
                         auto_execute=auto_execute)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    def post(self, base):
        request = Request(base + "/v1/tasks", data=json.dumps(self.payload).encode(),
                          headers={"Authorization": "Bearer test-only",
                                   "Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=4) as response:
            return json.load(response)

    def test_opt_out_enqueues_but_never_runs(self):
        base = self.start(False)
        task = self.post(base)
        self.assertEqual(task["status"], "PENDING")
        self.assertEqual(self.store.get(task["id"]).status, TaskStatus.PENDING)
        self.assertEqual(self.adapter.calls, 0)

    def test_explicit_worker_runs_and_persists_session_proof(self):
        base = self.start(True)
        task = self.post(base)
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            stored = self.store.get(task["id"])
            if stored and stored.status == TaskStatus.COMPLETED:
                break
            time.sleep(0.025)
        else:
            self.fail("Submitted task was never processed by worker")
        self.assertEqual(stored.session_id, "session_worker")
        self.assertEqual(stored.result["index_validation"]["index_state"], "CURRENT")
        self.assertEqual(stored.result["pie_mcp_evidence"][0]["tool"], "pie_project_status")
        self.assertEqual(self.adapter.calls, 1)
        self.assertEqual(self.post(base)["id"], task["id"])
        time.sleep(0.05)
        self.assertEqual(self.adapter.calls, 1)

    def test_startup_picks_persisted_pending_task(self):
        pending, _ = self.service.submit("client", self.payload)
        self.start(True)
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            state = self.store.get(pending.id)
            if state and state.status == TaskStatus.COMPLETED:
                break
            time.sleep(0.025)
        else:
            self.fail("Pending task not processed after startup")
        self.assertEqual(self.adapter.calls, 1)


if __name__ == "__main__":
    unittest.main()
