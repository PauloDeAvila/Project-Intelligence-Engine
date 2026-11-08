import json
import hmac
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pie.orchestrator.gateway import Gateway
from pie.orchestrator.models import TaskStatus
from pie.orchestrator.service import Execution, Orchestrator, ProjectPolicy
from pie.orchestrator.store import TaskStore


class FakeFreshness:
    def validate(self, project): return {"index_state": "CURRENT", "project": str(project.root)}


class FakeAdapter:
    def __init__(self): self.cancelled = []
    def execute(self, task, project, prompt, on_session=None):
        if on_session: on_session("ses_test")
        return Execution("ses_test", {"answer": "ok"}, {"input_tokens": 4, "output_tokens": 2})
    def cancel(self, session_id): self.cancelled.append(session_id)


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve(); self.store = TaskStore(root / "state.sqlite3"); self.addCleanup(self.store.close)
        self.adapter = FakeAdapter(); self.policy = ProjectPolicy("pie", root, frozenset({"nvidia/nemotron"}))
        self.service = Orchestrator(self.store, {"pie": self.policy}, self.adapter, FakeFreshness())
        self.payload = {"project_id": "pie", "task_type": "read_only_review", "model": "nvidia/nemotron", "idempotency_key": "one"}

    def test_idempotency_transitions_and_metrics(self):
        task, created = self.service.submit("client", self.payload); duplicate, again = self.service.submit("client", self.payload)
        self.assertTrue(created); self.assertFalse(again); self.assertEqual(task.id, duplicate.id)
        done = self.service.run(task.id)
        self.assertEqual(done.status, TaskStatus.COMPLETED)
        stored = self.store.get(task.id); self.assertEqual(stored.session_id, "ses_test"); self.assertEqual(stored.metrics["input_tokens"], 4)
        self.assertEqual([e["kind"] for e in self.store.events(task.id)], ["created", "state", "state", "state", "session_bound", "execution_recorded", "state", "state"])

    def test_recovery_blocks_interrupted_task(self):
        task, _ = self.service.submit("client", self.payload); self.store.transition(task.id, TaskStatus.VALIDATING); self.store.transition(task.id, TaskStatus.QUEUED); self.store.transition(task.id, TaskStatus.RUNNING)
        self.assertEqual(self.store.recover_interrupted(), 1)
        self.assertEqual(self.store.get(task.id).status, TaskStatus.BLOCKED)

    def test_rejects_unknown_fields_and_unauthorized_model(self):
        with self.assertRaises(ValueError): self.service.submit("client", self.payload | {"command": "whoami"})
        with self.assertRaises(PermissionError): self.service.submit("client", self.payload | {"model": "other", "idempotency_key": "two"})

    def test_loopback_gateway_status_cancel_and_sse(self):
        server = Gateway(("127.0.0.1", 0), self.service, "token", "gitlab")
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start(); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        request = Request(base + "/v1/tasks", data=json.dumps(self.payload).encode(), headers={"Authorization": "Bearer token", "Content-Type": "application/json"}, method="POST")
        with urlopen(request) as response: created = json.load(response)
        with self.assertRaises(HTTPError) as denied: urlopen(base + "/v1/tasks/" + created["id"])
        self.assertEqual(denied.exception.code, 401)
        with urlopen(Request(base + "/v1/tasks/" + created["id"] + "/cancel", data=b"", headers={"Authorization": "Bearer token"}, method="POST")) as response: self.assertEqual(json.load(response)["status"], "CANCELLED")
        with urlopen(Request(base + "/v1/tasks/" + created["id"] + "/events", headers={"Authorization": "Bearer token"})) as response: self.assertIn("event: created", response.read().decode())

    def test_gitlab_webhook_is_signed_mapped_and_idempotent(self):
        server = Gateway(("127.0.0.1", 0), self.service, "token", "secret", {"Issue Hook": self.payload | {"idempotency_key": "ignored"}})
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start(); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        raw, timestamp = b'{"untrusted":"content"}', str(int(__import__("time").time()))
        signature = hmac.new(b"secret", timestamp.encode() + b"." + raw, "sha256").hexdigest()
        headers = {"X-Gitlab-Event": "Issue Hook", "X-Gitlab-Event-UUID": "event-1", "X-Orchestrator-Timestamp": timestamp, "X-Orchestrator-Signature": signature}
        request = Request(f"http://127.0.0.1:{server.server_port}/v1/webhooks/gitlab", data=raw, headers=headers, method="POST")
        with urlopen(request) as response: first = json.load(response)
        with urlopen(request) as response: second = json.load(response)
        self.assertEqual(first["id"], second["id"])


if __name__ == "__main__": unittest.main()
