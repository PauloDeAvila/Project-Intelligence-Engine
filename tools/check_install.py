#!/usr/bin/env python3
"""Validate installation into an isolated target directory."""
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        target = pathlib.Path(directory) / "site"
        result = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-deps", "--no-build-isolation", "--target", str(target), str(ROOT)], cwd=ROOT, capture_output=True, text=True, check=False)
        if result.returncode:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            return result.returncode
        environment = dict(os.environ, PYTHONPATH=str(target))
        probe = subprocess.run([sys.executable, "-c", "import pie; print(pie.__version__)"], env=environment, capture_output=True, text=True, check=False)
        print(probe.stdout, end="")
        if probe.returncode:
            print(probe.stderr, file=sys.stderr)
        return probe.returncode


if __name__ == "__main__":
    raise SystemExit(main())

