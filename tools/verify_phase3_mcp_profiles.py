"""Run the exact MCP commands from temporary Phase 3 profiles, without Codex."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import tomllib


class Probe:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._drain, args=(process.stdout,), daemon=True).start()
        threading.Thread(target=self._drain_stderr, args=(process.stderr,), daemon=True).start()

    def _drain(self, stream) -> None:
        if stream is not None:
            for line in stream:
                self.lines.put(line)
        self.lines.put(None)

    @staticmethod
    def _drain_stderr(stream) -> None:
        if stream is not None:
            for _ in stream:
                pass

    def call(self, identifier: int, method: str, params: dict | None = None) -> dict:
        message = {"jsonrpc": "2.0", "id": identifier, "method": method}
        if params is not None:
            message["params"] = params
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                raw = self.lines.get(timeout=1)
            except queue.Empty:
                continue
            if raw is None:
                raise RuntimeError("MCP process exited before response")
            try:
                response = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if response.get("id") == identifier:
                return response
        raise TimeoutError(f"MCP response timeout for {method}")

    def notify(self, method: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.process.stdin.flush()

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                    capture_output=True, check=False, timeout=5,
                )
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        finally:
            for stream in (self.process.stdout, self.process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()


def _profile(path: Path, workspace: Path) -> tuple[dict, str, list[str], dict[str, str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    servers = data.get("mcp_servers")
    if not isinstance(servers, dict):
        raise ValueError("Profile must contain MCP servers")
    enabled = {name: value for name, value in servers.items()
               if isinstance(value, dict) and value.get("enabled", True) is not False}
    if len(enabled) != 1:
        raise ValueError("Profile must contain exactly one enabled MCP server")
    name, value = next(iter(enabled.items()))
    if not isinstance(value, dict) or not isinstance(value.get("command"), str):
        raise ValueError("MCP command missing")
    args = value.get("args")
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise ValueError("MCP args must be a string array")
    env = value.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise ValueError("MCP env must be a string table")
    command = value["command"]
    if ("\\" in command or "/" in command) and not Path(command).is_file():
        raise ValueError(f"MCP command unavailable: {command}")
    if ("\\" not in command and "/" not in command) and shutil.which(command) is None:
        raise ValueError(f"MCP command unavailable: {command}")
    gateway = "pie.gateway.domain" in args
    if gateway:
        source = env.get("PIE_SOURCE_ROOT")
        commit = env.get("PIE_SOURCE_COMMIT")
        pythonpath = env.get("PYTHONPATH")
        if not source or not commit or Path(pythonpath or "").resolve() != Path(source).resolve():
            raise ValueError("PIE source environment incomplete")
        source_path = Path(source).resolve(strict=True)
        git = subprocess.run(["git", "-C", str(source_path.parent), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=False, timeout=20)
        if git.returncode != 0 or len(commit) != 40:
            raise ValueError("PIE source commit mismatch")
        source_tree = subprocess.run(["git", "-C", str(source_path.parent), "diff", "--quiet",
                                      commit, "HEAD", "--", "src"],
                                     capture_output=True, text=True, check=False, timeout=20)
        if source_tree.returncode != 0:
            raise ValueError("PIE source tree mismatch")
        probe_env = dict(os.environ, PYTHONPATH=str(source_path))
        module = subprocess.run([command, "-c", "import pie; print(pie.__file__)"],
                                env=probe_env, capture_output=True, text=True, check=False, timeout=20)
        module_path = Path(module.stdout.strip()).resolve() if module.returncode == 0 and module.stdout.strip() else None
        if module_path is None or not module_path.is_relative_to(source_path):
            raise ValueError("PIE module resolves outside configured source")
    workspace_arg = args[args.index("--workspace") + 1] if "--workspace" in args else None
    if workspace_arg and Path(workspace_arg).resolve() != workspace.resolve():
        raise ValueError("Gateway workspace mismatch")
    return value, name, args, env


def verify_profile(path: Path, workspace: Path, *, tool: str, arguments: dict,
                   required_texts: list[str], followup_tool: str | None = None,
                   followup_arguments: dict | None = None) -> dict:
    value, server, args, configured_env = _profile(path, workspace)
    env = dict(os.environ)
    env.update(configured_env)
    command = [value["command"], *args]
    started = time.perf_counter()
    process = subprocess.Popen(command, cwd=workspace, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    probe = Probe(process)
    result = {"profile": str(path), "server": server, "tool": tool,
              "model_sessions_started": 0, "provider_usage_status": "not_applicable"}
    try:
        init = probe.call(1, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                               "clientInfo": {"name": "pie-offline-profile-probe", "version": "1"}})
        if "error" in init:
            raise RuntimeError("initialize returned an error")
        probe.notify("notifications/initialized")
        listed = probe.call(2, "tools/list", {})
        tools = listed.get("result", {}).get("tools", [])
        names = [item.get("name") for item in tools if isinstance(item, dict)]
        if tool not in names:
            raise RuntimeError(f"required tool missing: {tool}")
        called = probe.call(3, "tools/call", {"name": tool, "arguments": arguments})
        if called.get("result", {}).get("isError"):
            raise RuntimeError("tools/call returned MCP error")
        observed = called
        if followup_tool:
            observed = probe.call(4, "tools/call", {"name": followup_tool,
                                                    "arguments": followup_arguments or {}})
            if observed.get("result", {}).get("isError"):
                raise RuntimeError("follow-up tools/call returned MCP error")
        has_structured_content = "structuredContent" in observed.get("result", {})
        content = observed.get("result", {}).get("content", [])
        response_text = "\n".join(item.get("text", "") for item in content
                                    if isinstance(item, dict) and isinstance(item.get("text"), str))
        missing = [value for value in required_texts if value not in response_text]
        if missing:
            raise RuntimeError("fixture marker missing: " + ",".join(missing))
        response_state = None
        source_chars = None
        returned_chars = None
        try:
            payload = json.loads(response_text)
            if isinstance(payload, dict):
                response_state = payload.get("state")
                source_chars = payload.get("source_chars")
                returned_chars = payload.get("returned_chars")
        except json.JSONDecodeError:
            pass
        result.update({"status": "PASS", "initialize": "PASS", "tools_list": "PASS",
                       "tool_call": "PASS", "tool_count": len(names),
                       "followup_tool": followup_tool,
                       "required_texts": required_texts,
                       "required_texts_present": True,
                       "response_text_chars": len(response_text),
                       "structured_content_present": has_structured_content,
                       "response_state": response_state,
                       "source_chars": source_chars,
                       "returned_chars": returned_chars,
                       "duration_ms": round((time.perf_counter() - started) * 1000, 3)})
        return result
    finally:
        probe.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--arguments", default="{}")
    parser.add_argument("--require-text", action="append", default=[])
    parser.add_argument("--followup-tool")
    parser.add_argument("--followup-arguments", default="{}")
    parser.add_argument("profiles", nargs="+", type=Path)
    args = parser.parse_args()
    arguments = json.loads(args.arguments)
    followup_arguments = json.loads(args.followup_arguments)
    results = []
    try:
        for profile in args.profiles:
            results.append(verify_profile(profile, args.workspace.resolve(), tool=args.tool,
                                          arguments=arguments, required_texts=args.require_text,
                                          followup_tool=args.followup_tool,
                                          followup_arguments=followup_arguments))
    except (OSError, RuntimeError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "model_sessions_started": 0,
                          "reason": str(exc)[:240], "results": results}, indent=2))
        return 2
    print(json.dumps({"status": "PASS", "model_sessions_started": 0, "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
