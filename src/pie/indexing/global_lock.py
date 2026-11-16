"""Cross-process advisory file lock for the local global index.

Never executes arbitrary code. Windows msvcrt and POSIX fcntl are used only
to serialize independent PIE MCP sessions indexing the same workspace.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import time


@contextmanager
def workspace_index_lock(path: Path, timeout: float = 30.0):
    if not 0 < timeout <= 120:
        raise ValueError("Invalid workspace lock timeout")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b"\0")
            lock.flush()
        deadline = time.monotonic() + timeout
        locked = False
        try:
            while not locked:
                try:
                    if os.name == "nt":
                        import msvcrt
                        lock.seek(0)
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                except (BlockingIOError, OSError):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Global PIE workspace lock timed out")
                    time.sleep(.05)
            yield
        finally:
            if locked:
                if os.name == "nt":
                    import msvcrt
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
