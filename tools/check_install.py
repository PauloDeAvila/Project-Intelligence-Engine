#!/usr/bin/env python3
"""Validate installation into an isolated target directory."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import venv

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        environment_root = pathlib.Path(directory) / "environment"
        project_root = pathlib.Path(directory) / "sample-project"
        venv.EnvBuilder(with_pip=True).create(environment_root)
        scripts = environment_root / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        executable = scripts / ("pie.exe" if os.name == "nt" else "pie")
        install = subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", str(ROOT)], cwd=ROOT, capture_output=True, text=True, check=False)
        if install.stdout:
            print(install.stdout, end="")
        if install.returncode:
            if install.stderr:
                print(install.stderr, file=sys.stderr, end="")
            return install.returncode
        project_root.mkdir()
        (project_root / "app.py").write_text("class App:\n    def run(self):\n        return True\n", encoding="utf-8")
        commands = [
            ([str(executable), "--version"], "0.1.0"),
            ([str(executable), "init", "--root", str(project_root)], "initialized"),
            ([str(executable), "index", "--root", str(project_root)], "indexed"),
            ([str(executable), "status", "--root", str(project_root)], "status"),
            ([str(executable), "search", "App", "--root", str(project_root)], "search"),
            ([str(executable), "symbol", "App.run", "--root", str(project_root)], "symbol"),
        ]
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        environment["PATH"] = str(scripts) + os.pathsep + environment.get("PATH", "")
        for index, (command, kind) in enumerate(commands):
            result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False)
            if result.stdout:
                print(result.stdout, end="")
            if result.returncode:
                if result.stderr:
                    print(result.stderr, file=sys.stderr, end="")
                return result.returncode
            if index == 0:
                if result.stdout.strip() != "0.1.0":
                    print(f"Unexpected PIE version output: {result.stdout!r}", file=sys.stderr)
                    return 1
                continue
            payload = json.loads(result.stdout)
            valid = {
                "initialized": lambda value: value.get("status") == "initialized",
                "indexed": lambda value: value.get("files") == 1 and value.get("symbols") == 2,
                "status": lambda value: value.get("files") == 1 and value.get("symbols") == 2,
                "search": lambda value: any(item.get("qualified_name") == "App" for item in value),
                "symbol": lambda value: any(item.get("qualified_name") == "App.run" for item in value),
            }[kind](payload)
            if not valid:
                print(f"Unexpected output for installed PIE {kind}: {result.stdout}", file=sys.stderr)
                return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

