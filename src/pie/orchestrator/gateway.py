from __future__ import annotations

import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import time
from typing import Any

from .service import Orchestrator
from .store import TaskStore
from .models import TaskStatus


class Gateway(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], orchestrator: Orchestrator, admin_token: str, gitlab_secret: str, gitlab_map: dict[str, dict[str, Any]] | None = None, *, auto_execute: bool = False):
        if address[0] not in {"127.0.0.1", "::1", "localhost"}: raise ValueError("Gateway must bind to loopback")
        self.orchestrator, self.admin_token, self.gitlab_secret, self.gitlab_map = orchestrator, admin_token, gitlab_secret, gitlab_map or {}
        self.auto_execute = auto_execute
        self._wake = threading.Event()
        self._stop_worker = threading.Event()
        self._worker: threading.Thread | None = None
        super().__init__(address, Handler)

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        if self.auto_execute and self._worker is None:
            self._worker = threading.Thread(target=self._worker_loop, name="pie-task-worker", daemon=True)
            self._worker.start()
        super().serve_forever(poll_interval=poll_interval)

    def _worker_loop(self) -> None:
        store = TaskStore(self.orchestrator.store.path)
        try:
            agent = Orchestrator(store, self.orchestrator.projects, self.orchestrator.adapter,
                                 self.orchestrator.freshness, recover=False)
            while not self._stop_worker.is_set():
                row = store.connection.execute(
                    "SELECT id FROM tasks WHERE status=? ORDER BY priority DESC, created_at, id LIMIT 1",
                    (TaskStatus.PENDING,),
                ).fetchone()
                if row:
                    try:
                        agent.run(row["id"])
                    except Exception:
                        task = store.get(row["id"])
                        if task is not None and task.status in (TaskStatus.VALIDATING, TaskStatus.RUNNING):
                            store.transition(task.id, TaskStatus.FAILED, error="WorkerError")
                    continue
                self._wake.wait(timeout=1)
                self._wake.clear()
        finally:
            store.close()

    def notify_worker(self) -> None:
        if self.auto_execute:
            self._wake.set()

    def server_close(self) -> None:
        self._stop_worker.set()
        self._wake.set()
        if self._worker is not None:
            self._worker.join(timeout=2)
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    server: Gateway  # type: ignore[reportIncompatibleVariableOverride]
    def log_message(self, format: str, *_args: Any) -> None: pass
    def _json(self, code: int, value: Any) -> None:
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def _body(self) -> tuple[bytes, dict[str, Any]]:
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        value = json.loads(raw)
        if not isinstance(value, dict): raise ValueError("JSON object required")
        return raw, value
    def _admin(self) -> bool: return hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {self.server.admin_token}")
    def _task(self, task_id: str) -> dict[str, Any] | None:
        task = self.server.orchestrator.store.get(task_id)
        return task.__dict__ | {"status": task.status} if task else None
    def do_POST(self) -> None:
        try:
            if self.path == "/v1/webhooks/gitlab":
                raw, _ = self._body(); event = self.headers.get("X-Gitlab-Event", ""); event_id = self.headers.get("X-Gitlab-Event-UUID", ""); timestamp = self.headers.get("X-Orchestrator-Timestamp", "")
                if not event_id or event not in self.server.gitlab_map or not timestamp.isdigit() or abs(time.time() - int(timestamp)) > 300: self._json(401, {"error": "invalid_webhook"}); return
                expected = hmac.new(self.server.gitlab_secret.encode(), timestamp.encode() + b"." + raw, "sha256").hexdigest()
                if not hmac.compare_digest(self.headers.get("X-Orchestrator-Signature", ""), expected): self._json(401, {"error": "invalid_webhook"}); return
                payload = self.server.gitlab_map[event] | {"idempotency_key": event_id}
                task, created = self.server.orchestrator.submit("gitlab", payload); self.server.notify_worker(); self._json(202 if created else 200, self._task(task.id)); return
            if self.path == "/v1/tasks":
                if not self._admin(): self._json(401, {"error": "unauthorized"}); return
                _, body = self._body(); task, created = self.server.orchestrator.submit("client", body); self.server.notify_worker(); self._json(202 if created else 200, self._task(task.id)); return
            if self.path.startswith("/v1/tasks/") and self.path.endswith("/cancel"):
                if not self._admin(): self._json(401, {"error": "unauthorized"}); return
                task = self.server.orchestrator.cancel(self.path.split("/")[3]); self._json(200, self._task(task.id)); return
            self._json(404, {"error": "not_found"})
        except (ValueError, PermissionError) as exc: self._json(400, {"error": str(exc)})
        except KeyError: self._json(404, {"error": "not_found"})
    def do_GET(self) -> None:
        if not self._admin(): self._json(401, {"error": "unauthorized"}); return
        if self.path.startswith("/v1/tasks/") and self.path.endswith("/events"):
            task_id = self.path.split("/")[3]; data = "".join(f"event: {e['kind']}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n" for e in self.server.orchestrator.store.events(task_id))
            raw = data.encode(); self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        if self.path.startswith("/v1/tasks/"):
            value = self._task(self.path.split("/")[3]); self._json(200 if value else 404, value or {"error": "not_found"}); return
        self._json(404, {"error": "not_found"})
