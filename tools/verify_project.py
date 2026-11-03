#!/usr/bin/env python3
"""Fail-closed, standard-library CI validation runner. Configure ci/checks.json per project."""
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = ROOT / "ci" / "checks.json"
TIERS = ("unit", "component", "integration", "e2e", "regression", "build")

def validate_config(config):
    checks = config.get("checks")
    if not isinstance(checks, dict):
        raise ValueError("'checks' must be an object")
    for tier in TIERS:
        entry = checks.get(tier)
        if not isinstance(entry, dict):
            raise ValueError(f"Missing verification tier: {tier}")
        if entry.get("status") == "not-applicable":
            if not entry.get("reason", "").strip():
                raise ValueError(f"{tier}: not-applicable requires a reason")
            continue
        if entry.get("status") != "required":
            raise ValueError(f"{tier}: status must be required or not-applicable")
        command = entry.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(v, str) and v for v in command):
            raise ValueError(f"{tier}: required command must be a non-empty argument array")

def run(config):
    validate_config(config)
    results = []
    failure = False
    for tier in TIERS:
        entry = config["checks"][tier]
        if entry["status"] == "not-applicable":
            results.append({"tier": tier, "status": "not-applicable", "reason": entry["reason"]})
            continue
        start = time.monotonic()
        command = list(entry["command"])
        if command and command[0].lower() in {"python", "python3", "py"}:
            command[0] = sys.executable
        try:
            p = subprocess.run(command, cwd=ROOT, timeout=entry.get("timeout_seconds", 1200), check=False,
                               capture_output=True, text=True)
            code = p.returncode
            status = "passed" if code == 0 else "failed"
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, status, error = None, "blocked", str(exc)
        else:
            error = None
        results.append({"tier": tier, "status": status, "returncode": code, "seconds": round(time.monotonic()-start, 2), "command": command,
                        **({"error": error} if error is not None else {})})
        failure |= status != "passed"
    out = ROOT / "verification-results.json"
    out.write_text(json.dumps({"results": results}, indent=2) + "\n", encoding="utf-8")
    for result in results:
        print(result["tier"], result["status"])
    return 1 if failure else 0

if __name__ == "__main__":
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        sys.exit(run(data))
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as e:
        print(f"VERIFICATION BLOCKED: {e}", file=sys.stderr)
        sys.exit(1)
