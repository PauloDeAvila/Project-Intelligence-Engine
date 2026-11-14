"""Real Playwright MCP/Chromium local-site probe through PIE web domain gateway.

No model/provider calls; no external website navigation. A local HTTP fixture
is served on 127.0.0.1 and browsed by an actual Playwright MCP process.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from queue import Empty,Queue
import re
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread

SCHEMA="pie-playwright-mcp-real-browser-v1"


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/","/index.html"):
            self.send_error(404)
            return
        html=("<html><head><title>PIE Browser Fixture</title></head><body>"
              "<main><h1>Local Fixture</h1><form>"
              '<input aria-label="Search materials" />'
              '<button type="button">Inspect scene</button>'
              "</form>"
              +"".join(f'<p><a href="/item-{i}">Material item {i}</a></p>' for i in range(160))
              +"</main></body></html>").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self,*args):
        pass


class MCPClient:
    def __init__(self,process):
        self.process=process
        self.output=Queue()
        self.stderr=Queue()
        self.thread=Thread(target=self._reader,args=(process.stdout,self.output),daemon=True)
        self.errthread=Thread(target=self._reader,args=(process.stderr,self.stderr),daemon=True)
        self.thread.start()
        self.errthread.start()

    @staticmethod
    def _reader(stream,queue):
        for line in stream:
            queue.put(line)
        queue.put(None)

    def call(self,id_,method,params=None,timeout=100):
        q={"jsonrpc":"2.0","id":id_,"method":method}
        if params is not None:q["params"]=params
        self.process.stdin.write(json.dumps(q,separators=(",",":"))+"\n")
        self.process.stdin.flush()
        while True:
            try:raw=self.output.get(timeout=timeout)
            except Empty as exc:raise TimeoutError("MCP timeout") from exc
            if raw is None:raise RuntimeError("Playwright MCP exited before responding")
            try:response=json.loads(raw)
            except json.JSONDecodeError:continue
            if response.get("id")==id_:return response

    def notify(self,method):
        self.process.stdin.write(json.dumps({"jsonrpc":"2.0","method":method})+"\n")
        self.process.stdin.flush()

    def close(self):
        self.process.stdin.close()
        try:self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def main()->int:
    server=ThreadingHTTPServer(("127.0.0.1",0),Fixture)
    runner=Thread(target=server.serve_forever,daemon=True)
    runner.start()
    with tempfile.TemporaryDirectory(prefix="pie-real-web-") as folder:
        root=Path(os.environ.get("PIE_PROBE_WORKSPACE", str(Path(folder)/"project")))
        root.mkdir(parents=True, exist_ok=True)
        (root/"pyproject.toml").write_text("[project]\nname='real-browser'\n",encoding="utf-8")
        store=Path(os.environ.get("PIE_PROBE_STORE", str(Path(folder)/"pie-global")))
        args=[sys.executable,"-m","pie.gateway.domain","serve","--domain","web",
              "--workspace",str(root),"--store",str(store),
              "--max-chars","1300","--",*sys.argv[1:]]
        if len(sys.argv)<=1:raise RuntimeError("Provide real Playwright MCP argv")
        env=dict(os.environ,PIE_GLOBAL_STORAGE_ROOT=str(store))
        client=None
        try:
            process=subprocess.Popen(args,cwd=root,env=env,stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                     text=True,encoding="utf-8",bufsize=1)
            client=MCPClient(process)
            init=client.call(1,"initialize",{
                "protocolVersion":"2025-03-26",
                "capabilities":{},
                "clientInfo":{"name":"pie-live-web-probe","version":"1"}
            })
            if "error" in init:raise RuntimeError("MCP initialization rejected")
            client.notify("notifications/initialized")
            tools=client.call(2,"tools/list",{})
            names={t.get("name") for t in tools.get("result",{}).get("tools",[])
                   if isinstance(t,dict)}
            if not {"browser_navigate","browser_snapshot","pie_gateway_output_get"}.issubset(names):
                raise RuntimeError("Expected browser/navigation/recovery tools not listed")
            target="http://127.0.0.1:"+str(server.server_port)+"/"
            navigated=client.call(3,"tools/call",{"name":"browser_navigate",
                                                 "arguments":{"url":target}})
            snapshot=client.call(4,"tools/call",{"name":"browser_snapshot","arguments":{}})
            if navigated.get("result",{}).get("isError") or snapshot.get("result",{}).get("isError"):
                raise RuntimeError("Browser navigation/snapshot tool failed")
            content=snapshot.get("result",{}).get("content",[])
            if len(content)!=1 or content[0].get("type")!="text":
                raise RuntimeError("Expected one Playwright text snapshot")
            observation=content[0]["text"]
            try:compact=json.loads(observation)
            except json.JSONDecodeError:raise RuntimeError("Web snapshot was not optimized")
            if compact.get("pie_gateway")!="v1" or not isinstance(compact.get("web"),dict):
                raise RuntimeError("Web gateway did not return a recoverable snapshot")
            if "ref=e" not in compact.get("preview",""):
                raise RuntimeError("Browser native references were not preserved")
            result=client.call(5,"tools/call",{
                "name":"pie_gateway_output_get",
                "arguments":{"output_id":compact["output_id"],"max_chars":1300}})
            if result.get("result",{}).get("isError"):
                raise RuntimeError("Page recovery failed")
            piece=json.loads(result["result"]["content"][0]["text"])
            if piece.get("total_chars",0)<=len(observation):
                raise RuntimeError("No reduction on the local browser snapshot")
            saved=compact["source_chars"]-len(observation)
            report={"schema":SCHEMA,"state":"PASS","server":"actual_playwright_mcp",
                    "browser_navigation_executed":True,
                    "browser_snapshot_executed":True,
                    "tool_recovery_executed":True,
                    "native_ref_retained":True,
                    "source_chars":compact["source_chars"],
                    "model_facing_chars":len(observation),
                    "saved_chars":saved,
                    "reduction_percent":round(100*saved/compact["source_chars"],3),
                    "provider_tokens_measured":False,
                    "note":"Real local browser call; character ratio not model token savings"}
            print("PIE_WEB_LIVE_REPORT="+json.dumps(report,separators=(",",":")),flush=True)
            return 0
        except Exception as exc:
            print("PIE_WEB_LIVE_REPORT="+json.dumps({
                "schema":SCHEMA,"state":"FAIL","error_type":type(exc).__name__,
                "provider_tokens_measured":False}),flush=True)
            return 1
        finally:
            if client:client.close()
            server.shutdown()
            server.server_close()


if __name__=="__main__":
    raise SystemExit(main())
