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
        web_import = subprocess.run(
            [str(python), "-c", "import pie.web; print(pie.web.WEB_CONTRACT_SCHEMA)"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if web_import.stdout:
            print(web_import.stdout, end="")
        if web_import.returncode or web_import.stdout.strip() != "pie-web-contracts-v1":
            if web_import.stderr:
                print(web_import.stderr, file=sys.stderr, end="")
            print("Installed package is missing the phase-0 web contract schema", file=sys.stderr)
            return web_import.returncode or 1
        project_root.mkdir()
        (project_root / "app.py").write_text(
            "APP_NAME = \"app\"\n\nclass App:\n    def run(self):\n        return APP_NAME\n",
            encoding="utf-8",
        )
        commands = [
            ([str(executable), "--version"], "0.1.0"),
            ([str(executable), "init", "--root", str(project_root)], "initialized"),
            ([str(executable), "index", "--root", str(project_root)], "indexed"),
            ([str(executable), "status", "--root", str(project_root)], "status"),
            ([str(executable), "search", "App", "--root", str(project_root)], "search"),
            ([str(executable), "symbol", "App.run", "--root", str(project_root)], "symbol"),
            ([str(executable), "definitions", "App", "--root", str(project_root)], "definitions"),
            ([str(executable), "references", "APP_NAME", "--root", str(project_root)], "references"),
            ([str(executable), "analysis", "--root", str(project_root)], "analysis"),
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
                "definitions": lambda value: value.get("query") == "App"
                and any(item.get("qualified_name") == "App" for item in value.get("definitions", [])),
                "references": lambda value: value.get("query") == "APP_NAME"
                and any(item.get("consumer_symbol") == "App.run" for item in value.get("references", [])),
                "analysis": lambda value: value.get("definitions", 0) > 0 and value.get("dangling_targets") == 0,
            }[kind](payload)
            if not valid:
                print(f"Unexpected output for installed PIE {kind}: {result.stdout}", file=sys.stderr)
                return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

