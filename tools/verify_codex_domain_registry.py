"""Prove native Codex CLI accepts both scoped PIE domain MCP registrations.

No model call and no upstream browser/Blender process is started. All settings
are written to a temporary CODEX_HOME on the CI runner.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main() -> int:
    codex=shutil.which("codex")
    if not codex:
        print(json.dumps({"state":"FAIL","reason":"codex_unavailable"}))
        return 2
    with tempfile.TemporaryDirectory(prefix="pie-domain-codex-") as temp:
        env=dict(os.environ,CODEX_HOME=str(Path(temp)))
        entries={
            "pie-domain-blender":("blender",["uvx","mcp-for-blender"]),
            "pie-domain-web":("web",["npx","@playwright/mcp@0.0.85"]),
        }
        observed={}
        for name,(domain,upstream) in entries.items():
            args=[sys.executable,"-m","pie.gateway.domain","serve",
                  "--domain",domain,"--max-chars","1200","--",*upstream]
            try:
                added=subprocess.run([codex,"mcp","add",name,"--",*args],
                                    env=env,capture_output=True,text=True,timeout=20)
                got=subprocess.run([codex,"mcp","get",name,"--json"],
                                  env=env,capture_output=True,text=True,timeout=20)
            except (OSError,subprocess.TimeoutExpired):
                observed[name]=False
                continue
            if added.returncode or got.returncode:
                observed[name]=False
                continue
            try:
                obj=json.loads(got.stdout)
                transport=obj.get("transport",{})
                actual=transport.get("args",[])
                observed[name]=(transport.get("type")=="stdio" and
                                "pie.gateway.domain" in actual and
                                "--domain" in actual and
                                actual[actual.index("--domain")+1]==domain)
            except (TypeError,ValueError,KeyError,IndexError):
                observed[name]=False
        ok=all(observed.values()) and len(observed)==2
        print(json.dumps({"schema":"pie-domain-codex-registry-v1",
                          "state":"PASS" if ok else "FAIL",
                          "registered_domains":observed,
                          "provider_calls":0,
                          "note":"Real Codex CLI config registration only; upstream not invoked"}))
        return 0 if ok else 1


if __name__=="__main__":
    raise SystemExit(main())
