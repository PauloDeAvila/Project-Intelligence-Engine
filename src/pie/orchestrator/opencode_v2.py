"""OpenCode 2.2.x REST adapter: /api contract, not legacy /session routes.

A final idle success AND recorded PIE MCP output are both required.
This module does not expose raw source or MCP responses publicly.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from .models import Task
from .service import Execution, ProjectPolicy


class OpenCodeV2Adapter:
    def __init__(self, base_url: str, password: str):
        url = urlparse(base_url)
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"}
                or url.path not in ("", "/") or url.username or url.password
                or url.query or url.fragment or not password):
            raise ValueError("OpenCode v2 must use authenticated HTTP loopback")
        self.base_url = base_url.rstrip("/")
        self.password = password
        self.session_dirs: dict[str, Path] = {}

    def _request(self, method: str, path: str,
                 body: dict[str, Any] | None = None) -> Any:
        encoded = json.dumps(body).encode() if body is not None else None
        auth = base64.b64encode(("opencode:" + self.password).encode()).decode()
        req = Request(self.base_url + "/api" + path, method=method, data=encoded,
                      headers={"Authorization": "Basic " + auth,
                               "Accept": "application/json",
                               "Content-Type": "application/json"})
        with urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            if resp.status == 204:
                return None
            if "application/json" not in content_type.lower():
                raise ValueError("OpenCode v2 returned non-JSON API response")
            return json.loads(raw)

    @staticmethod
    def _data(response: Any) -> Any:
        if not isinstance(response, dict) or "data" not in response:
            raise ValueError("OpenCode v2 response lacks data envelope")
        return response["data"]

    @staticmethod
    def _location_matches(response: dict[str, Any], root: Path) -> bool:
        location = response.get("location")
        if not isinstance(location, dict):
            return False
        directory = location.get("directory")
        return isinstance(directory, str) and Path(directory).resolve() == root.resolve()

    @staticmethod
    def _evidence(messages: Any, pie_name: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if not isinstance(messages, list):
            raise ValueError("OpenCode v2 messages must be an array")
        proofs: list[dict[str, Any]] = []
        terminal: dict[str, Any] | None = None
        tokens = None
        for message in messages:
            if not isinstance(message, dict):
                continue
            kind = message.get("type")
            if kind == "assistant":
                if message.get("error"):
                    raise RuntimeError("OpenCode v2 assistant error")
                for part in message.get("content", []):
                    if not isinstance(part, dict) or part.get("type") != "tool":
                        continue
                    name = part.get("name")
                    state = part.get("state")
                    if name in {"bash", "edit", "write", "apply_patch", "webfetch", "websearch", "task"}:
                        raise RuntimeError("Forbidden tool invocation in OpenCode trace")
                    if not isinstance(name, str) or not isinstance(state, dict):
                        continue
                    accepted = {pie_name + "_project_status",
                                pie_name + "_pie_project_status",
                                "mcp__" + pie_name + "__pie_project_status"}
                    if state.get("status") == "error" and name in accepted:
                        raise RuntimeError("PIE MCP call failed")
                    if state.get("status") != "completed":
                        continue
                    if name not in accepted:
                        continue
                    output = state.get("content")
                    if not isinstance(output, list) or not output:
                        raise RuntimeError("PIE MCP output missing")
                    raw = json.dumps(output, ensure_ascii=False, sort_keys=True).encode()
                    if len(raw) > 1_000_000:
                        raise RuntimeError("PIE MCP output exceeds proof limit")
                    proofs.append({"tool": name, "tool_call_id": part.get("id"),
                                   "status": "completed",
                                   "output_sha256": hashlib.sha256(raw).hexdigest(),
                                   "output_bytes": len(raw)})
                if message.get("finish") == "stop":
                    terminal = {"assistant_message_id": message.get("id"),
                                "finish_reason": "stop"}
                    value = message.get("tokens")
                    tokens = value if isinstance(value, dict) else None
                elif message.get("finish") in ("length", "error", "content-filter"):
                    raise RuntimeError("OpenCode v2 assistant did not finish normally")
            if kind == "idle":
                if message.get("outcome") != "succeeded":
                    raise RuntimeError("OpenCode v2 session ended unsuccessfully")
                if terminal is None or not proofs:
                    raise RuntimeError("OpenCode v2 lacks completed PIE MCP proof")
                return {**terminal, "pie_mcp_evidence": proofs,
                        "message_count": len(messages)}, tokens
        raise RuntimeError("OpenCode v2 session has no verified successful idle marker")

    def execute(self, task: Task, project: ProjectPolicy, prompt: str,
                on_session: Callable[[str], None] | None = None) -> Execution:
        root = project.root.resolve()
        # This service must be launched from the authorized PIE directory.
        mcp = self._request("GET", "/mcp")
        if not isinstance(mcp, dict) or not self._location_matches(mcp, root):
            raise RuntimeError("OpenCode v2 active location differs from PIE root")
        servers = self._data(mcp)
        if not isinstance(servers, list) or not any(
            isinstance(item, dict) and item.get("name") == project.pie_mcp_name
            and item.get("status") == "connected" for item in servers
        ):
            raise RuntimeError("PIE MCP is not connected in OpenCode v2")
        provider, slash, model = task.model.partition("/")
        if not slash or not provider or not model:
            raise ValueError("Expected provider/model")
        created = self._request("POST", "/session",
                                {"title": "orchestrator-" + task.id,
                                 "location": {"directory": str(root)},
                                 "model": {"providerID": provider, "modelID": model}})
        session = self._data(created)
        if not isinstance(session, dict) or not isinstance(session.get("id"), str):
            raise RuntimeError("OpenCode v2 did not return session ID")
        session_id = session["id"]
        session_location = session.get("location")
        if (not isinstance(session_location, dict) or
                not isinstance(session_location.get("directory"), str) or
                Path(session_location["directory"]).resolve() != root):
            raise RuntimeError("OpenCode v2 session is not in the authorized project")
        self.session_dirs[session_id] = root
        if on_session is not None:
            on_session(session_id)
        sid = quote(session_id, safe="")
        admitted = self._request("POST", "/session/" + sid + "/prompt",
                                 {"text": prompt, "resume": True})
        inbox = self._data(admitted)
        if not isinstance(inbox, dict):
            raise ValueError("OpenCode v2 did not admit prompt")
        deadline = time.monotonic() + task.timeout_seconds
        while time.monotonic() < deadline:
            # /api/session/active tracks *foreground* drains, not future state.
            active = self._data(self._request("GET", "/session/active"))
            if not isinstance(active, dict):
                raise ValueError("OpenCode v2 active map invalid")
            if session_id not in active:
                messages_response = self._request(
                    "GET", "/session/" + sid + "/message?" +
                    urlencode({"order": "asc", "limit": "100"}))
                if not isinstance(messages_response, dict):
                    raise ValueError("OpenCode v2 message response invalid")
                cursor = messages_response.get("cursor")
                if isinstance(cursor, dict) and cursor.get("next"):
                    raise RuntimeError("OpenCode v2 transcript paginated; not certified")
                messages = self._data(messages_response)
                try:
                    result, metrics = self._evidence(messages, project.pie_mcp_name)
                    return Execution(session_id, result, metrics)
                except RuntimeError as exc:
                    if "no verified successful idle marker" not in str(exc):
                        raise
            time.sleep(0.5)
        try:
            self.cancel(session_id)
        except Exception:
            pass
        raise TimeoutError("OpenCode v2 task exceeded deadline")

    def cancel(self, session_id: str) -> None:
        sid = quote(session_id, safe="")
        result = self._request("POST", "/session/" + sid + "/interrupt")
        if not isinstance(result, dict):
            raise ValueError("OpenCode v2 interrupt contract mismatch")
