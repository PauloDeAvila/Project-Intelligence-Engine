#!/usr/bin/env python3
"""Produce a reproducible local indexing baseline without asserting a universal limit."""
import argparse
import ctypes
import json
import os
import pathlib
import shutil
import sys
import tempfile
import tracemalloc
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pie.indexing.indexer import index_project
from pie.interfaces.cli import command_search
from pie.scanning.discovery import IGNORED_DIRECTORIES


def peak_process_rss_bytes() -> int:
    """Return process peak resident memory using platform APIs from the stdlib."""
    if os.name == "nt":
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_process_memory_info = psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
        get_process_memory_info.restype = wintypes.BOOL
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        if not get_process_memory_info(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.PeakWorkingSetSize)

    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--files", type=int, help="generate this many synthetic Python modules")
    source_group.add_argument("--source", type=pathlib.Path, help="copy and benchmark an existing Python project")
    parser.add_argument("--queries", type=int, default=20)
    args = parser.parse_args()
    files = args.files if args.files is not None else 100
    if files < 1 or args.queries < 0:
        parser.error("--files must be positive and --queries cannot be negative")
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        source_kind = "synthetic"
        if args.source is not None:
            source = args.source.resolve()
            if not source.is_dir():
                parser.error("--source must name an existing directory")
            source_kind = "project"
            for current, directories, filenames in os.walk(source, topdown=True):
                current_path = pathlib.Path(current)
                directories[:] = [
                    name for name in directories
                    if name not in IGNORED_DIRECTORIES and not (current_path / name).is_symlink()
                ]
                for name in filenames:
                    input_path = current_path / name
                    if input_path.is_symlink():
                        continue
                    if name == ".gitignore" or input_path.suffix.lower() == ".py":
                        relative = input_path.relative_to(source)
                        output_path = root / relative
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(input_path, output_path)
        else:
            for number in range(files):
                module = root / f"package_{number % 100:03d}" / f"module_{number:05d}.py"
                module.parent.mkdir(parents=True, exist_ok=True)
                module.write_text(
                    f"import pathlib\n\nclass Service{number}:\n"
                    f"    def run(self, root: pathlib.Path) -> int:\n        return {number}\n",
                    encoding="utf-8",
                )
        tracemalloc.start()
        start = time.perf_counter()
        result = index_project(root)
        elapsed = time.perf_counter() - start
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        query_start = time.perf_counter()
        for _ in range(args.queries):
            command_search(root, "Service")
        query_seconds = time.perf_counter() - query_start
        print(json.dumps({"source_kind": source_kind, "files": result["files"], "symbols": result["symbols"], "index_seconds": round(elapsed, 4), "tracemalloc_peak_bytes": peak_bytes, "peak_process_rss_bytes": peak_process_rss_bytes(), "queries": args.queries, "query_seconds": round(query_seconds, 4)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

