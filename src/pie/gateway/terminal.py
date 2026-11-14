"""One-shot terminal adapter: one invocation, bounded capture, recoverable output.

Not a system-wide shell interceptor: the client must route its commands through
this wrapper or install the documented RTK native hook. Commands are argument
vectors (shell=False). The wrapper never grants permissions or retries commands.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from pie.gateway.policy import reduce_text
from pie.gateway.rtk_adapter import wrap_command
from pie.indexing.global_workspace import detect_workspace
from pie.storage.locations import ENV_HOME, global_home

MAX_CAPTURE_PER_STREAM = 200_000


def _capture(pipe, ceiling: int, output: dict, key: str) -> None:
    buffer = bytearray()
    discarded = 0
    try:
        while True:
            chunk = pipe.read(16384)
            if not chunk:
                break
            keep = max(0, min(len(chunk), ceiling - len(buffer)))
            if keep:
                buffer.extend(chunk[:keep])
            discarded += len(chunk) - keep
    finally:
        pipe.close()
        output[key] = {"text": bytes(buffer).decode("utf-8", "replace"),
                       "captured_bytes": len(buffer),
                       "discarded_bytes": discarded}


def run_command(root: Path, command: list[str], *, max_chars: int = 2500,
                timeout_seconds: float = 120.0, rtk: str = "auto") -> tuple[int, dict]:
    if not command:
        raise ValueError("No executable supplied")
    if not 1 <= timeout_seconds <= 3600:
        raise ValueError("timeout_seconds must be 1..3600")
    root = detect_workspace(root)
    args, used_rtk = wrap_command(command, rtk)
    started = time.perf_counter()
    result: dict = {}
    process = subprocess.Popen(args, cwd=root, shell=False, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None and process.stderr is not None
    threads = [
        threading.Thread(target=_capture, args=(process.stdout, MAX_CAPTURE_PER_STREAM, result, "stdout")),
        threading.Thread(target=_capture, args=(process.stderr, MAX_CAPTURE_PER_STREAM, result, "stderr"))
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        code = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
        code = 124
    for thread in threads:
        thread.join()
    stdout, stderr = result["stdout"], result["stderr"]
    source = ("STDOUT:\n" + stdout["text"] + "\nSTDERR:\n" + stderr["text"])
    observed = reduce_text(root, source, surface="terminal",
                           tool=Path(command[0]).name, kind="terminal",
                           max_chars=max_chars, exit_code=code)
    discarded = stdout["discarded_bytes"] + stderr["discarded_bytes"]
    if discarded:
        observed["state"] = "CAPTURE_TRUNCATED"
        observed["capture_complete"] = False
        observed["recovery"] = "partial_capture_only"
        observed["discarded_bytes"] = discarded
    else:
        observed["capture_complete"] = True
    if timed_out:
        observed["state"] = "TIMED_OUT"
        observed["capture_complete"] = False
    observed["rtk_applied"] = used_rtk
    observed["command_name"] = Path(command[0]).name
    observed["elapsed_ms"] = round((time.perf_counter()-started)*1000, 3)
    observed["measurement"] = "characters_not_model_tokens"
    return code, observed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PIE one-shot terminal output gateway")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--store", type=Path, default=None)
    parser.add_argument("--rtk", choices=("auto","off","required"), default="auto")
    parser.add_argument("--max-chars", type=int, default=2500)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    opts = parser.parse_args(argv)
    command = opts.command
    if command and command[0] == "--":
        command = command[1:]
    os.environ[ENV_HOME] = str((opts.store or global_home()).resolve())
    try:
        code, data = run_command(opts.workspace, command,
                                 max_chars=opts.max_chars,
                                 timeout_seconds=opts.timeout_seconds,
                                 rtk=opts.rtk)
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({"state":"NOT_EXECUTED","reason":f"{type(exc).__name__}: {exc}"},
                         ensure_ascii=False))
        return 125
    print(json.dumps(data, ensure_ascii=False, separators=(",",":")))
    return code if 0 <= code <= 255 else 1


if __name__ == "__main__":
    raise SystemExit(main())
