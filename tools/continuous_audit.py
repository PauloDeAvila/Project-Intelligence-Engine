#!/usr/bin/env python3
"""Read-only change audit. Reports evidence; never changes repository files."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def line_endings(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    crlf = data.count(b"\r\n")
    lone_lf = data.count(b"\n") - crlf
    return crlf, lone_lf


def run() -> int:
    base = os.environ.get("AUDIT_BASE", "").strip()
    head = os.environ.get("AUDIT_HEAD", "HEAD").strip()
    if not base:
        print("AUDIT_BASE is required", file=sys.stderr)
        return 2
    try:
        git("rev-parse", "--verify", f"{base}^{{commit}}")
        git("rev-parse", "--verify", f"{head}^{{commit}}")
        changed = git("diff", "--name-only", "--diff-filter=ACMRT", "-z", base, head).stdout
        paths = [p.decode("utf-8", "replace") for p in changed.split(b"\0") if p]
        check = git("diff", "--check", base, head, check=False)
        stat = git("diff", "--numstat", "-z", base, head).stdout.decode("utf-8", "replace")
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.decode("utf-8", "replace"), file=sys.stderr)
        return 2

    errors: list[str] = []
    warnings: list[str] = []
    if check.returncode:
        errors.append("git diff --check failed (whitespace/conflict issues): " +
                      check.stdout.decode("utf-8", "replace")[:4000])
    for relative in paths:
        file = Path(relative)
        if not file.is_file() or file.is_symlink():
            continue
        if file.suffix.lower() not in {".py", ".md", ".toml", ".yaml", ".yml", ".json", ".sh"}:
            continue
        if file.stat().st_size > 5_000_000:
            warnings.append(f"Large text file not scanned: {relative}")
            continue
        crlf, lf = line_endings(file)
        if crlf and lf:
            errors.append(f"Mixed CRLF/LF line endings: {relative} (CRLF={crlf}, LF={lf})")
        elif crlf:
            warnings.append(f"CRLF in text file: {relative} (check repository conventions)")
    if any(p.startswith(".github/workflows/") for p in paths):
        warnings.append("GitHub Actions workflow changed; review permissions and triggers")
    if any(p.endswith(("requirements.txt", "pyproject.toml", "poetry.lock", "uv.lock")) for p in paths):
        warnings.append("Dependencies/build metadata changed; review supply-chain impact")
    if len(paths) > 100:
        warnings.append(f"Large change set ({len(paths)} files); consider focused review")

    report = {
        "schema_version": 1,
        "base": base,
        "head": head,
        "changed_files": paths,
        "changed_files_count": len(paths),
        "diff_numstat": stat[:30000],
        "errors": errors,
        "warnings": warnings,
        "status": "failed" if errors else "passed",
    }
    Path("continuous-audit-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    lines = [
        "## Continuous change audit",
        f"**Status:** {report['status']} | **Changed files:** {len(paths)}",
        f"**Base:** `{base}` | **Head:** `{head}`",
        "",
        "### Errors",
        *([f"- {x}" for x in errors] if errors else ["- None detected by these checks"]),
        "",
        "### Warnings",
        *([f"- {x}" for x in warnings] if warnings else ["- None"]),
        "",
        "_Scope: Git diff hygiene and text line endings only. Not a full security or test audit._",
    ]
    summary = "\n".join(lines) + "\n"
    Path("continuous-audit-summary.md").write_text(summary, encoding="utf-8", newline="\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write(summary)
    print(summary)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(run())
