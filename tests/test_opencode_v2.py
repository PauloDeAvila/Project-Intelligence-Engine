"""OpenCode v2.2.x API contract fixtures; no real model/network required."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pie.orchestrator.models import TaskStatus
from pie.orchestrator.opencode_v2 import OpenCodeV2Adapter
from pie.orchestrator.service import Orchestrator, ProjectPolicy
from pie.orchestrator.store import TaskStore


def messages():
    return [
        {"type": "user", "id": "msg_u", "text": "read index"},
        {"type": "assistant", "id": "msg_a", "finish": "tool-calls",
         "content": [{"type": "tool", "id": "call_1", "name": "pie_project_status",
                       "state": {"status": "completed",
                                 "content": [{"type": "text", "text": "CURRENT"}]}}]},
        {"type": "assistant", "id": "msg_end", "finish": "stop",
         "tokens": {"input": 40, "output": 7},
         "content": [{"type": "text", "text": "Project is CURRENT"}]},
        {"type": "idle", "outcome": "succeeded"}
    ]


class FakeV2(OpenCodeV2Adapter):
    def __init__(self, root, transcript):
        super().__init__("http://127.0.0.1:4097", "test-password")
        self.root = root
        self.transcript = transcript
        self.calls = []

    def _request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path == "/mcp":
            return {"location": {"directory": str(self.root)},
                    "data": [{"name": "pie", "status": {"status": "connected"}}]}
        if path == "/session" and method == "POST":
            return {"data": {"id": "ses_v2", "location": {"directory": str(self.root)}}}
        if path.endswith("/prompt"):
            return {"data": {"id": "inbox_1"}}
        if path == "/session/active":
            return {"data": {}}
        if path.startswith("/session/ses_v2/message?"):
            return {"data": self.transcript, "cursor": {"next": None}}
        if path.endswith("/interrupt"):
            return {"interrupted": False}
        raise AssertionError("Unexpected API request " + method + " " + path)


class OpenCodeV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = TaskStore(self.root / "store.sqlite3")
        self.addCleanup(self.store.close)
        self.project = ProjectPolicy("pie", self.root,
                                     frozenset({"opencode/nemotron-3.5-lightning-free"}))

    def make_task(self, adapter):
        service = Orchestrator(self.store, {"pie": self.project}, adapter,
                               type("Fresh", (), {"validate": lambda _, project: {"index_state": "CURRENT"}})())
        task, _ = service.submit("client", {
            "project_id": "pie", "model": "opencode/nemotron-3.5-lightning-free",
            "task_type": "read_only_review", "idempotency_key": "one",
        })
        return service, task

    def test_verified_v2_completion(self):
        adapter = FakeV2(self.root, messages())
        service, task = self.make_task(adapter)
        done = service.run(task.id)
        self.assertEqual(done.status, TaskStatus.COMPLETED)
        self.assertEqual(done.session_id, "ses_v2")
        self.assertEqual(done.metrics["input"], 40)
        proof = done.result["pie_mcp_evidence"][0]
        self.assertEqual(proof["tool"], "pie_project_status")
        raw = json.dumps([{"type": "text", "text": "CURRENT"}],
                         ensure_ascii=False, sort_keys=True).encode()
        self.assertEqual(proof["output_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(adapter.calls[0][1], "/mcp")
        self.assertIn(("POST", "/session/ses_v2/prompt",
                       {"text": unittest.mock.ANY, "resume": True}), adapter.calls)

    def test_v2_model_claim_not_proof(self):
        data = [{"type": "assistant", "id": "a", "finish": "stop",
                 "content": [{"type": "text", "text": "I called PIE"}]},
                {"type": "idle", "outcome": "succeeded"}]
        adapter = FakeV2(self.root, data)
        service, task = self.make_task(adapter)
        done = service.run(task.id)
        self.assertEqual(done.status, TaskStatus.FAILED)
        self.assertEqual(done.session_id, "ses_v2")

    def test_doctor_mesh_not_proof(self):
        data = messages()
        data[1]["content"][0]["name"] = "pie_doctor_mesh_project_status"
        with self.assertRaisesRegex(RuntimeError, "PIE MCP"):
            OpenCodeV2Adapter._evidence(data, "pie")

    def test_failed_idle_is_not_success(self):
        data = messages()
        data[-1]["outcome"] = "failed"
        with self.assertRaisesRegex(RuntimeError, "unsuccessfully"):
            OpenCodeV2Adapter._evidence(data, "pie")

    def test_pagination_is_not_certified(self):
        class Paginated(FakeV2):
            def _request(self, method, path, body=None):
                answer = super()._request(method, path, body)
                if "/message?" in path:
                    answer["cursor"]["next"] = "next"
                return answer
        service, task = self.make_task(Paginated(self.root, messages()))
        self.assertEqual(service.run(task.id).status, TaskStatus.FAILED)
