"""Narrow client for an already-isolated, loopback-only OpenCode server."""
from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .service import Execution, ProjectPolicy
from .models import Task


class OpenCodeHttpAdapter:
    def __init__(self, base_url: str, password: str):
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}: raise ValueError("OpenCode must be loopback HTTP")
        self.base_url, self.password = base_url.rstrip("/"), password

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        request = Request(self.base_url + path, data=data, method=method, headers={"Authorization": "Basic " + __import__("base64").b64encode(f"opencode:{self.password}".encode()).decode(), "Content-Type": "application/json"})
        with urlopen(request, timeout=30) as response:
            value = json.loads(response.read())
            if not isinstance(value, dict): raise ValueError("OpenCode returned an invalid response")
            return value

    def execute(self, task: Task, project: ProjectPolicy, prompt: str) -> Execution:
        session = self._request("POST", "/session", {"directory": str(project.root), "title": f"orchestrator-{task.id}"})
        session_id = session.get("id")
        if not isinstance(session_id, str): raise ValueError("OpenCode did not create a session")
        provider, _, model = task.model.partition("/")
        if not provider or not model: raise ValueError("Model must be provider/model")
        self._request("POST", f"/session/{session_id}/prompt_async", {"parts": [{"type": "text", "text": prompt}], "model": {"providerID": provider, "modelID": model}})
        deadline = time.monotonic() + task.timeout_seconds
        while time.monotonic() < deadline:
            state = self._request("GET", f"/session/{session_id}")
            if state.get("status") in {"idle", "completed"}: return Execution(session_id, {"session": state}, state.get("usage") if isinstance(state.get("usage"), dict) else None)
            time.sleep(0.5)
        self.cancel(session_id)
        raise TimeoutError("OpenCode task timed out")

    def cancel(self, session_id: str) -> None:
        self._request("POST", f"/session/{session_id}/abort", {})
