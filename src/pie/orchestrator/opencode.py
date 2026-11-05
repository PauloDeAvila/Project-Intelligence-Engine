"""OpenCode loopback HTTP adapter with verifiable completion and early session binding."""
from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .models import Task
from .service import Execution, ProjectPolicy


class OpenCodeHttpAdapter:
    def __init__(self, base_url: str, password: str):
        parsed = urlparse(base_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/")):
            raise ValueError("OpenCode must be an HTTP loopback server without extra URL components")
        self.base_url, self.password = base_url.rstrip("/"), password
        self._session_dirs: dict[str, Path] = {}

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None, directory: Path | None = None) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        auth = base64.b64encode(f"opencode:{self.password}".encode()).decode()
        headers = {"Authorization": "Basic " + auth, "Content-Type": "application/json"}
        if directory is not None:
            headers["X-OpenCode-Directory"] = quote(str(directory), safe="")
        request = Request(self.base_url + path, data=data, method=method, headers=headers)
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            # POST /session/:id/prompt_async and some abort endpoints return 204.
            if response.status == 204 or not raw:
                return None
            return json.loads(raw)

    @staticmethod
    def _finished(
        messages: Any, pie_mcp_name: str = "pie"
    ) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None]:
        """Trust recorded tool events, not assistant prose claiming MCP usage."""
        if not isinstance(messages, list):
            raise ValueError("OpenCode message listing is not an array")
        evidence: list[dict[str, Any]] = []
        final: dict[str, Any] | None = None
        metrics: dict[str, Any] | None = None
        prohibited = {"bash", "edit", "write", "apply_patch",
                      "webfetch", "websearch", "task"}
        for message in messages:
            if not isinstance(message, dict):
                continue
            info = message.get("info")
            if not isinstance(info, dict) or info.get("role") != "assistant":
                continue
            if info.get("error"):
                raise RuntimeError("OpenCode assistant reported execution error")
            for part in message.get("parts", []):
                if not isinstance(part, dict) or part.get("type") != "tool":
                    continue
                name = part.get("tool", part.get("name"))
                if not isinstance(name, str):
                    continue
                if name in prohibited:
                    raise RuntimeError("Forbidden tool invocation reported by OpenCode")
                state = part.get("state")
                if not isinstance(state, dict) or state.get("status") != "completed":
                    continue
                prefix = f"{pie_mcp_name}_"
                mcp_prefix = f"mcp__{pie_mcp_name}__"
                if not (name.startswith(prefix) or name.startswith(mcp_prefix)):
                    continue
                output = state.get("output", state.get("content"))
                if output is None:
                    continue
                raw = (output.encode("utf-8") if isinstance(output, str)
                       else json.dumps(output, sort_keys=True, ensure_ascii=False).encode("utf-8"))
                if not raw or len(raw) > 1_000_000:
                    raise RuntimeError("PIE MCP tool output missing or exceeds proof bound")
                evidence.append({
                    "tool": name,
                    "tool_call_id": part.get("callID", part.get("id")),
                    "status": "completed",
                    "output_sha256": hashlib.sha256(raw).hexdigest(),
                    "output_bytes": len(raw),
                })
            finish = info.get("finish")
            if finish is not None:
                if finish not in ("stop", "end_turn", "complete"):
                    if finish not in ("tool-calls", "tool_calls", "unknown"):
                        raise RuntimeError("OpenCode generation did not finish normally")
                    continue
                final = {"assistant_message_id": info.get("id"),
                         "finish_reason": finish,
                         "message_count": len(messages)}
                tokens = info.get("tokens")
                metrics = tokens if isinstance(tokens, dict) else None
        if final is None:
            return False, None, None
        if not evidence:
            raise RuntimeError("No completed PIE MCP tool output in OpenCode session")
        final["pie_mcp_evidence"] = evidence
        return True, final, metrics

    def execute(self, task: Task, project: ProjectPolicy, prompt: str,
                on_session: Callable[[str], None] | None = None) -> Execution:
        provider, separator, model = task.model.partition("/")
        if not separator or not provider or not model:
            raise ValueError("Model must be provider/model")
        mcp = self._request("GET", "/mcp", directory=project.root)
        if not isinstance(mcp, dict):
            raise RuntimeError("Invalid OpenCode MCP status")
        pie_mcp = mcp.get(project.pie_mcp_name)
        if not isinstance(pie_mcp, dict) or pie_mcp.get("status") != "connected":
            raise RuntimeError("Required PIE MCP is not connected for the project")
        session = self._request("POST", "/session",
                                {"title": f"orchestrator-{task.id}"}, project.root)
        if not isinstance(session, dict) or not isinstance(session.get("id"), str):
            raise ValueError("OpenCode did not create a session")
        session_id = session["id"]
        session_root = session.get("directory")
        if not isinstance(session_root, str) or Path(session_root).resolve() != project.root.resolve():
            raise RuntimeError("OpenCode returned a different project directory")
        self._session_dirs[session_id] = project.root
        if on_session is not None:
            on_session(session_id)
        sid = quote(session_id, safe="")
        # Explicitly deny built-in destructive tools in the agent payload.
        # Further host-level permissions must still be verified on Windows.
        tools = {"bash": False, "edit": False, "write": False, "apply_patch": False,
                 "webfetch": False, "websearch": False, "task": False}
        self._request("POST", f"/session/{sid}/prompt_async",
                      {"parts": [{"type": "text", "text": prompt}],
                       "model": {"providerID": provider, "modelID": model},
                       "tools": tools}, project.root)
        deadline = time.monotonic() + task.timeout_seconds
        while time.monotonic() < deadline:
            status_map = self._request("GET", "/session/status", directory=project.root)
            if not isinstance(status_map, dict):
                raise ValueError("OpenCode returned invalid session status map")
            status = status_map.get(session_id)
            if status is not None:
                if not isinstance(status, dict):
                    raise ValueError("OpenCode returned invalid session status")
                if status.get("type") == "busy":
                    time.sleep(0.5)
                    continue
                if status.get("type") not in ("idle",):
                    # Retry/pending states are not completion.
                    time.sleep(0.5)
                    continue
            # Absence in status map commonly means idle. Require terminal
            # assistant message nonetheless to avoid false positives.
            messages = self._request("GET", f"/session/{sid}/message", directory=project.root)
            done, result, metrics = self._finished(messages, project.pie_mcp_name)
            if done and result is not None:
                return Execution(session_id, result, metrics)
            time.sleep(0.5)
        try:
            self.cancel(session_id)
        except Exception:
            pass
        raise TimeoutError("OpenCode did not produce a verified completed assistant message")

    def cancel(self, session_id: str) -> None:
        directory = self._session_dirs.get(session_id)
        self._request("POST", f"/session/{quote(session_id, safe='')}/abort", {}, directory)
