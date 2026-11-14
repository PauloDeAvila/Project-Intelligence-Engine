"""Use the REAL Codex CLI to register and read a PIE MCP proxy, without login.

This only proves Codex accepts our stdio command registration. It cannot prove
provider tool calls, local Blender access, authentication, or token savings.
"""
from __future__ import annotations
import json,os,subprocess,sys,tempfile
from pathlib import Path

def main()->int:
    with tempfile.TemporaryDirectory(prefix="pie-real-codex-mcp-") as tmp:
        home=Path(tmp)
        env=dict(os.environ,CODEX_HOME=str(home))
        command=[sys.executable,"-m","pie.gateway.mcp_stdio",
                 "--max-chars","1200","--compress-tool","get_scene_info",
                 "--",sys.executable,"-c","import sys"]
        put=subprocess.run(["codex","mcp","add","pie-smoke","--",*command],
                           env=env,capture_output=True,text=True,timeout=40)
        if put.returncode:
            print(json.dumps({"state":"FAIL","step":"mcp_add","code":put.returncode}))
            return 1
        get=subprocess.run(["codex","mcp","get","pie-smoke","--json"],
                           env=env,capture_output=True,text=True,timeout=40)
        if get.returncode:
            print(json.dumps({"state":"FAIL","step":"mcp_get","code":get.returncode}))
            return 1
        try:
            data=json.loads(get.stdout)
        except json.JSONDecodeError:
            print(json.dumps({"state":"FAIL","step":"mcp_get_json"}))
            return 1
        transport=data.get("transport",{}) if isinstance(data,dict) else {}
        args=transport.get("args",[]) if isinstance(transport,dict) else []
        passed=(isinstance(args,list) and "pie.gateway.mcp_stdio" in args
                and "get_scene_info" in args)
        print(json.dumps({"schema":"pie-codex-actual-cli-registry-v1",
                          "state":"PASS" if passed else "FAIL",
                          "codex_cli_executed":True,
                          "mcp_registration_found":passed,
                          "provider_api_calls":0,
                          "note":"CLI registration only; not end-to-end tool use"}))
        return 0 if passed else 1
if __name__=="__main__":raise SystemExit(main())
