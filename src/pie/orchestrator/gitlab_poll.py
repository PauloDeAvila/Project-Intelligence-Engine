"""Outbound-only GitLab issue polling bridge for the local PIE/OpenCode orchestrator.

MVP deliberately ignores issue title/body/URL. No HTTP listener, inbound
tunnel, shell command, or dynamic agent prompt comes from GitLab issues.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .__main__ import PieFreshness
from .models import TERMINAL, TaskStatus
from .opencode import OpenCodeHttpAdapter
from .opencode_v2 import OpenCodeV2Adapter
from .service import Orchestrator, ProjectPolicy
from .store import TaskStore


class GitLabClient:
    """Limited HTTPS API client; never follows untrusted issue-supplied links."""

    def __init__(self, token: str, project_id: int):
        if not token or not isinstance(project_id, int) or project_id <= 0:
            raise ValueError("GitLab token and positive numeric project ID required")
        self.token = token
        self.project_id = project_id
        self.base = f"https://gitlab.com/api/v4/projects/{project_id}"

    def _request(self, method: str, path: str, fields: dict[str, str] | None = None) -> Any:
        data = urlencode(fields).encode("utf-8") if fields is not None else None
        request = Request(
            self.base + path,
            data=data,
            headers={"PRIVATE-TOKEN": self.token,
                     "Content-Type": "application/x-www-form-urlencoded"},
            method=method,
        )
        with urlopen(request, timeout=15) as response:
            if method == "GET" and response.headers.get("X-Next-Page"):
                raise RuntimeError("GitLab result exceeds first page; refusing incomplete scan")
            return json.load(response)

    def issues(self, label: str) -> list[dict[str, Any]]:
        query = urlencode({"labels": label, "state": "opened", "per_page": "100", "scope": "all"})
        rows = self._request("GET", "/issues?" + query)
        if not isinstance(rows, list):
            raise ValueError("Malformed GitLab issue list")
        return rows

    def notes(self, iid: int) -> list[dict[str, Any]]:
        rows = self._request("GET", f"/issues/{iid}/notes?per_page=100")
        if not isinstance(rows, list):
            raise ValueError("Malformed GitLab notes response")
        return rows

    def post_note(self, iid: int, body: str) -> None:
        self._request("POST", f"/issues/{iid}/notes", {"body": body})


def safe_poll_config(config: dict[str, Any]) -> dict[str, Any]:
    """Require explicit source/project/user allowlists; never accept source prompts."""
    setting = config.get("gitlab_poll")
    if not isinstance(setting, dict):
        raise ValueError("gitlab_poll configuration missing")
    expected = {"project_id", "label", "allowed_author_ids", "task", "token_env"}
    if set(setting) != expected:
        raise ValueError("gitlab_poll fields must match safe schema exactly")
    project_id = setting["project_id"]
    authors = setting["allowed_author_ids"]
    label = setting["label"]
    task = setting["task"]
    if type(project_id) is not int or project_id <= 0:
        raise ValueError("Positive numeric GitLab project ID required")
    if (not isinstance(label, str) or
            re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", label) is None):
        raise ValueError("Invalid fixed trigger label")
    if (not isinstance(authors, list) or not authors or any(
            type(x) is not int or x <= 0 for x in authors)):
        raise ValueError("Explicit allowed GitLab author IDs required")
    if (not isinstance(task, dict) or
            set(task) != {"project_id", "task_type", "model"} or
            not all(isinstance(value, str) and value for value in task.values())):
        raise ValueError("Fixed task policy required")
    name = setting["token_env"]
    if not isinstance(name, str) or re.fullmatch(r"[A-Z][A-Z0-9_]{2,80}", name) is None:
        raise ValueError("Invalid token environment variable")
    return setting


def report_note(task: Any) -> str:
    """Publish only status and narrow counters, not model content or error text."""
    metrics = task.metrics if isinstance(task.metrics, dict) else {}
    counts = {k: v for k in ("input_tokens", "output_tokens", "total_tokens")
              if type(v := metrics.get(k)) is int and v >= 0}
    marker = f"<!-- pie-orchestrator-task:{task.id} -->"
    return (marker + "\nPIE local agent result (fixed read-only review)\n\n"
            + f"- Task: `{task.id}`\n- Status: `{task.status.value}`\n"
            + f"- Provider-reported counters: `{json.dumps(counts, sort_keys=True)}`\n"
            + "- Raw source, prompts and credentials are not published.\n")


def run_once(
    config: dict[str, Any],
    api: GitLabClient,
    orchestrator: Orchestrator,
    *,
    execute: bool = False,
) -> dict[str, int]:
    setting = safe_poll_config(config)
    permitted = set(setting["allowed_author_ids"])
    stats = {"seen": 0, "rejected": 0, "created": 0, "executed": 0, "notified": 0}
    for issue in api.issues(setting["label"]):
        stats["seen"] += 1
        if not isinstance(issue, dict):
            stats["rejected"] += 1
            continue
        iid = issue.get("iid")
        author = issue.get("author")
        # Validate project and label again, not just server-side filters.
        if (type(iid) is not int or iid <= 0 or
                issue.get("project_id") != setting["project_id"] or
                not isinstance(author, dict) or
                author.get("id") not in permitted or
                not isinstance(issue.get("labels"), list) or
                setting["label"] not in issue["labels"]):
            stats["rejected"] += 1
            continue
        task_payload = dict(setting["task"])
        task_payload["idempotency_key"] = f"gitlab-project-{setting['project_id']}-issue-{iid}"
        task, created = orchestrator.submit("gitlab_poll", task_payload)
        if created:
            stats["created"] += 1
        if execute and task.status == TaskStatus.PENDING:
            task = orchestrator.run(task.id)
            stats["executed"] += 1
        if task.status in TERMINAL:
            marker = f"<!-- pie-orchestrator-task:{task.id} -->"
            if not any(marker in str(row.get("body", "")) for row in api.notes(iid)
                       if isinstance(row, dict)):
                api.post_note(iid, report_note(task))
                stats["notified"] += 1
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GitLab issue polling via outbound HTTPS only")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Explicitly enable local OpenCode execution; default queues tasks only")
    parser.add_argument("--interval", type=int, default=0,
                        help="0 = one scan; >=30 = keep polling at this interval")
    args = parser.parse_args(argv)
    if args.interval and args.interval < 30:
        parser.error("poll interval must be >=30 seconds")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    setting = safe_poll_config(config)
    token = os.environ.get(setting["token_env"], "")
    if not token:
        raise SystemExit("GitLab token missing from local environment")
    projects = {
        item["id"]: ProjectPolicy(item["id"], Path(item["root"]).resolve(),
                                 frozenset(item["models"]), pie_mcp_name=item.get("pie_mcp_name", "pie"))
        for item in config["projects"]
    }
    target = setting["task"]
    if (target["project_id"] not in projects or
            target["model"] not in projects[target["project_id"]].models or
            target["task_type"] not in projects[target["project_id"]].task_types):
        raise SystemExit("GitLab task not covered by local project policy")
    password = os.environ.get(config["opencode_password_env"], "")
    if not password:
        raise SystemExit("OpenCode server password missing")
    store = TaskStore(Path(config["state_db"]).expanduser())
    try:
        orchestrator = Orchestrator(
            store, projects,
            (OpenCodeV2Adapter if config.get("opencode_api_version", 2) == 2 else OpenCodeHttpAdapter)(config["opencode_url"], password),
            PieFreshness(),
        )
        api = GitLabClient(token, setting["project_id"])
        while True:
            stats = run_once(config, api, orchestrator, execute=args.execute)
            print(json.dumps(stats, sort_keys=True), flush=True)
            if not args.interval:
                return 0
            time.sleep(args.interval)
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
