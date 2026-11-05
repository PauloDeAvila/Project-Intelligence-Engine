from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .gateway import Gateway
from .opencode import OpenCodeHttpAdapter
from .service import Orchestrator, ProjectPolicy
from .store import TaskStore


class PieFreshness:
    def validate(self, project: ProjectPolicy):
        for command in ("index", "status"):
            result = subprocess.run([sys.executable, "-m", "pie", command, "--root", str(project.root)], capture_output=True, text=True, check=False, timeout=120)
            if result.returncode: raise RuntimeError(f"PIE {command} failed")
        value = json.loads(result.stdout)
        if value.get("index_state") != "CURRENT": raise RuntimeError(f"PIE freshness is {value.get('index_state')}")
        return {"index_state": value["index_state"], "files": value.get("files"), "symbols": value.get("symbols")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local OpenCode orchestration gateway.")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("host") not in {"127.0.0.1", "::1", "localhost"}: raise SystemExit("host must be loopback")
    projects = {entry["id"]: ProjectPolicy(entry["id"], Path(entry["root"]).resolve(), frozenset(entry["models"]), pie_mcp_name=entry.get("pie_mcp_name", "pie")) for entry in config["projects"]}
    admin = os.environ[config["admin_token_env"]]; password = os.environ[config["opencode_password_env"]]
    store = TaskStore(Path(config["state_db"]).expanduser())
    adapter = OpenCodeHttpAdapter(config["opencode_url"], password)
    server = Gateway((config["host"], int(config["port"])), Orchestrator(store, projects, adapter, PieFreshness()), admin, os.environ.get(config.get("gitlab_secret_env", ""), ""), config.get("gitlab_event_map", {}))
    try: server.serve_forever()
    finally: store.close()
    return 0


if __name__ == "__main__": raise SystemExit(main())
