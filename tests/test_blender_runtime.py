from pathlib import Path

import pie.certification.blender_runtime as runtime


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_existing_endpoint_is_reused_without_starting(monkeypatch):
    started = []
    monkeypatch.setattr(runtime.socket, "create_connection", lambda *args, **kwargs: _Connection())
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *args, **kwargs: started.append(True))

    result = runtime.ensure_blender_mcp(environment={"BLENDER_MCP_PORT": "9987"})

    assert result == {"state": "PASS", "host": "127.0.0.1", "port": 9987, "started": False}
    assert started == []


def test_missing_endpoint_starts_explicit_executable(monkeypatch, tmp_path):
    executable = tmp_path / "blender.exe"
    executable.write_text("test", encoding="utf-8")
    attempts = iter((OSError("down"), _Connection()))
    calls = []

    def connect(*args, **kwargs):
        value = next(attempts)
        if isinstance(value, Exception):
            raise value
        return value

    class Process:
        pid = 4321

    monkeypatch.setattr(runtime.socket, "create_connection", connect)
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *args, **kwargs: (calls.append((args, kwargs)) or Process()))

    result = runtime.ensure_blender_mcp(executable=executable, timeout_s=1)

    assert result["state"] == "PASS"
    assert result["started"] is True
    assert result["pid"] == 4321
    assert calls[0][0] == ([str(executable)],)


def test_missing_executable_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime.socket, "create_connection", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("down")))

    result = runtime.ensure_blender_mcp(executable=tmp_path / "missing.exe")

    assert result["state"] == "FAIL"
    assert result["reason"] == "BLENDER_EXECUTABLE_UNAVAILABLE"
