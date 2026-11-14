"""PIE Phase 1 terminal and MCP gateway contract/e2e tests.

Provider tokens, real Blender scenes and real Codex hook behavior are NOT
simulated as certified live measurements.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))

from pie.gateway.install import registration_plan, register_mcp
from pie.gateway.metrics import report
from pie.gateway.mcp_stdio import MCPStdioGateway, recovery_page, RECOVERY_NAME
from pie.gateway.policy import mcp_compactable, reduce_text
from pie.gateway.rtk_adapter import wrap_command
from pie.gateway.terminal import run_command
from pie.retrieval.output_pipeline import recover_output


def req(i, method, params=None):
    packet={"jsonrpc":"2.0","id":i,"method":method}
    if params is not None:
        packet["params"]=params
    return packet


class Phase1GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.root=self.base/"sample"
        self.root.mkdir()
        (self.root/"pyproject.toml").write_text("[project]\nname='phase1'\n",encoding="utf8")
        self.store=self.base/"pie-global"
        self.env=patch.dict(os.environ,{"PIE_GLOBAL_STORAGE_ROOT":str(self.store)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_offline_fixture_reduction_and_exact_recovery(self):
        from tools.benchmark_phase1_gateway import measure
        result=measure(max_chars=1200)
        self.assertEqual(result["functional_gate"],"PASS")
        self.assertTrue(result["sanitized_source_recovered_exactly"])
        self.assertTrue(result["exit_code_preserved"])
        self.assertTrue(result["secret_placeholder_not_returned"])
        self.assertGreater(result["character_reduction_percent"],80)
        self.assertFalse(result["provider_tokens_measured"])

    def test_generic_compact_and_recover_exact_sanitized(self):
        original="OK\n"*500 + "Authorization: Bearer super-private-credential\n" + "FAILED: expected 23, got 22\n"
        r=reduce_text(self.root,original,surface="terminal",tool="pytest",
                      kind="test",exit_code=1,max_chars=800)
        self.assertEqual(r["state"],"PARTIAL")
        self.assertEqual(r["exit_code"],1)
        self.assertIn("FAILED",r["text"])
        restored=recover_output(self.root,r["output_id"])
        self.assertNotIn("super-private-credential",restored["text"])
        self.assertIn("[REDACTED]",restored["text"])
        self.assertNotIn("Bearer super-private-credential",r["text"])
        r2=reduce_text(self.root,original,surface="terminal",tool="pytest",
                       kind="test",exit_code=1,max_chars=800)
        self.assertEqual(r["output_id"],r2["output_id"])

    def test_metrics_are_characters_not_provider_tokens(self):
        reduce_text(self.root,"x\n"*1200,surface="terminal",tool="unit",
                    max_chars=800)
        metrics=report(self.root)
        self.assertEqual(metrics["measurement"],"characters_not_model_tokens")
        self.assertEqual(metrics["events"],1)
        self.assertIsNone(metrics["provider_prompt_tokens"])
        self.assertGreater(metrics["groups"][0]["saved_chars"],0)

    def test_terminal_exactly_once_exit_and_recovery(self):
        marker=self.root/"called.txt"
        program=("from pathlib import Path; import sys; "
                 "p=Path(sys.argv[1]);p.write_text(p.read_text()+'1' if p.exists() else '1');"
                 "print('stage ok\\n'*200); print('assertion failed',file=sys.stderr); sys.exit(7)")
        code,data=run_command(self.root,[sys.executable,"-c",program,str(marker)],
                              rtk="off",max_chars=900)
        self.assertEqual(code,7)
        self.assertEqual(marker.read_text(),"1")
        self.assertEqual(data["exit_code"],7)
        self.assertTrue(data["capture_complete"])
        self.assertFalse(data["rtk_applied"])
        self.assertIn("STDERR:",recover_output(self.root,data["output_id"])["text"])

    def test_terminal_timeout_has_no_false_success(self):
        code,data=run_command(
            self.root,[sys.executable,"-c","import time;time.sleep(3)"],
            rtk="off",timeout_seconds=1,max_chars=800)
        self.assertEqual(code,124)
        self.assertEqual(data["state"],"TIMED_OUT")
        self.assertFalse(data["capture_complete"])

    def test_rtk_candidate_and_unknown_do_not_repeat_execution(self):
        with patch("pie.gateway.rtk_adapter.shutil.which",return_value="/mock/rtk"):
            cmd,enabled=wrap_command(["git","status"],"auto")
            self.assertEqual(cmd,["/mock/rtk","git","status"])
            self.assertTrue(enabled)
            fallback,wrapped=wrap_command(["unknown-tool","--version"],"auto")
            self.assertEqual(fallback,["unknown-tool","--version"])
            self.assertFalse(wrapped)
            with self.assertRaises(RuntimeError):
                wrap_command(["unknown-tool"],"required")
        with patch("pie.gateway.rtk_adapter.shutil.which",return_value=None):
            self.assertEqual(wrap_command(["git","status"],"auto")[0],
                             ["git","status"])

    def test_terminal_truncated_capture_is_never_claimed_complete(self):
        code,data=run_command(
            self.root,[sys.executable,"-c","print('x'*280000)"],
            rtk="off",max_chars=850)
        self.assertEqual(code,0)
        self.assertEqual(data["state"],"CAPTURE_TRUNCATED")
        self.assertFalse(data["capture_complete"])
        self.assertGreater(data["discarded_bytes"],0)
        self.assertEqual(data["recovery"],"partial_capture_only")

    def test_required_rtk_failure_executes_nothing(self):
        marker=self.root/"must-not-exist"
        with self.assertRaises(RuntimeError):
            run_command(self.root,["unrecognized-command",str(marker)],
                        rtk="required",max_chars=800)
        self.assertFalse(marker.exists())

    def test_oversize_never_claims_recoverability(self):
        result=reduce_text(self.root,"A"*500001,surface="terminal",tool="huge",max_chars=800)
        self.assertEqual(result["state"],"CAPTURE_LIMIT_EXCEEDED")
        self.assertIsNone(result["output_id"])
        self.assertEqual(result["recovery"],"unavailable_for_oversized_output")

    def test_mcp_structured_binary_error_and_json_passthrough(self):
        allowed=frozenset({"get_scene_info"})
        sample={"result":{"content":[{"type":"text","text":"Material "*400}]}}
        self.assertTrue(mcp_compactable(sample,"get_scene_info",allowed))
        self.assertFalse(mcp_compactable(sample,"edit_blender_code",allowed))
        self.assertFalse(mcp_compactable({"error":{"code":-32000}}, "get_scene_info",allowed))
        self.assertFalse(mcp_compactable({"result":{"content":[{"type":"text","text":"x"}],
                                      "isError":True}}, "get_scene_info",allowed))
        self.assertFalse(mcp_compactable({"result":{"content":[{"type":"image","data":"xyz"}]}},
                                        "get_scene_info",allowed))
        self.assertFalse(mcp_compactable({"result":{"content":[{"type":"text","text":"hi"}],
                                      "structuredContent":{"ok":True}}},
                                        "get_scene_info",allowed))
        self.assertFalse(mcp_compactable({"result":{"content":[{"type":"text","text":'{"ok": 1}'}]}},
                                        "get_scene_info",allowed))
        self.assertFalse(mcp_compactable(sample,"get_scene_info",allowed,has_output_schema=True))

    def test_install_dryrun_and_no_clobber(self):
        cmd=registration_plan("guarded-blender",["python","-m","blender_server"],
                              python=sys.executable,compress_tools=("get_scene_info",))
        self.assertEqual(cmd[:4],["codex","mcp","add","guarded-blender"])
        self.assertIn("pie.gateway.mcp_stdio",cmd)
        self.assertEqual(cmd[-3:],["python","-m","blender_server"])
        output=register_mcp("guarded",["python","-m","server"],python=sys.executable)
        self.assertEqual(output["state"],"DRY_RUN")
        with self.assertRaises(ValueError):
            registration_plan("bad command!",["x"],python=sys.executable)

    def _mcp(self, inputs: list[dict], marker: Path | None = None):
        script=r"""
import json,os,sys
from pathlib import Path
marker=os.environ.get("PIE_MCP_TEST_MARKER")
for line in sys.stdin:
    req=json.loads(line)
    if "id" not in req:
        continue
    method=req.get("method")
    if method=="initialize":
        body={"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"mock","version":"1"}}
    elif method=="tools/list":
        body={"tools":[
            {"name":"get_scene_info","inputSchema":{"type":"object"}},
            {"name":"execute_blender_code","inputSchema":{"type":"object"}},
            {"name":"get_struct","inputSchema":{"type":"object"},"outputSchema":{"type":"object"}},
            {"name":"get_json","inputSchema":{"type":"object"}},
            {"name":"get_error","inputSchema":{"type":"object"}},
            {"name":"get_image","inputSchema":{"type":"object"}}
        ]}
    elif method=="tools/call":
        if marker:
            p=Path(marker)
            p.write_text(p.read_text()+"x" if p.exists() else "x")
        name=req["params"]["name"]
        if name=="get_scene_info":
            body={"content":[{"type":"text","text":"Scene\\n"+"Cube roughness 0.35\\n"*180}]}
        elif name=="get_struct":
            body={"content":[{"type":"text","text":"status: ok "*450}],"structuredContent":{"materials":2}}
        elif name=="get_json":
            body={"content":[{"type":"text","text":json.dumps({"rows":[1]*800})}]}
        elif name=="get_error":
            body={"isError":True,"content":[{"type":"text","text":"Error: failed "*450}]}
        elif name=="get_image":
            body={"content":[{"type":"image","data":"abc","mimeType":"image/png"}]}
        else:
            body={"content":[{"type":"text","text":"Material created "*350}]}
    else:
        body={}
    print(json.dumps({"jsonrpc":"2.0","id":req["id"],"result":body}),flush=True)
"""
        env=dict(os.environ)
        env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1]/"src")
        if marker:
            env["PIE_MCP_TEST_MARKER"]=str(marker)
        cmd=[sys.executable,"-m","pie.gateway.mcp_stdio",
             "--workspace",str(self.root),"--store",str(self.store),
             "--max-chars","1000","--compress-tool","get_scene_info",
             "--compress-tool","get_struct","--compress-tool","get_json",
             "--compress-tool","get_error","--",
             sys.executable,"-u","-c",script]
        return subprocess.run(cmd,input="\n".join(json.dumps(x) for x in inputs)+"\n",
                              env=env,timeout=25,text=True,capture_output=True)

    def test_stdio_end_to_end_no_double_execution(self):
        marker=self.root/"calls.txt"
        calls=[
            req(1,"initialize",{}),
            {"jsonrpc":"2.0","method":"notifications/initialized"},
            req(2,"tools/list",{}),
            req(3,"tools/call",{"name":"get_scene_info","arguments":{}}),
            req(4,"tools/call",{"name":"execute_blender_code","arguments":{"code":"print(1)"}}),
            req(5,"tools/call",{"name":"get_struct","arguments":{}}),
            req(6,"tools/call",{"name":"get_json","arguments":{}}),
            req(7,"tools/call",{"name":"get_error","arguments":{}}),
            req(8,"tools/call",{"name":"get_image","arguments":{}}),
        ]
        done=self._mcp(calls,marker)
        self.assertEqual(done.returncode,0,done.stderr)
        lines=[json.loads(s) for s in done.stdout.splitlines()]
        messages={x["id"]:x for x in lines if "id" in x}
        self.assertEqual(len(messages),8, "STDERR: "+done.stderr+" STDOUT: "+done.stdout[:3000])
        self.assertEqual(len(marker.read_text()),6)
        self.assertEqual(messages[1]["result"]["serverInfo"]["name"],"mock")
        names=[x["name"] for x in messages[2]["result"]["tools"]]
        self.assertIn(RECOVERY_NAME,names)
        compact=json.loads(messages[3]["result"]["content"][0]["text"])
        self.assertEqual(compact["pie_gateway"],"v1")
        self.assertEqual(compact["tool"],"get_scene_info")
        self.assertEqual(compact["state"],"PARTIAL")
        self.assertIsNotNone(compact["output_id"])
        self.assertNotIn("pie_gateway",messages[4]["result"]["content"][0]["text"])
        self.assertEqual(messages[5]["result"]["structuredContent"],{"materials":2})
        self.assertTrue(messages[6]["result"]["content"][0]["text"].startswith("{"))
        self.assertTrue(messages[7]["result"]["isError"])
        self.assertEqual(messages[8]["result"]["content"][0]["type"],"image")

        # Recovery may be requested by a fresh MCP process: the source is
        # persistent, sanitized and isolated by the workspace hash.
        recovery=req(9,"tools/call",{"name":RECOVERY_NAME,"arguments":{
            "output_id":compact["output_id"],"max_chars":1000}})
        recovered=self._mcp([recovery],marker)
        self.assertEqual(recovered.returncode,0,recovered.stderr)
        self.assertEqual(len(marker.read_text()),6)
        page=json.loads(json.loads(recovered.stdout)["result"]["content"][0]["text"])
        self.assertEqual(page["output_id"],compact["output_id"])
        self.assertLessEqual(len(json.dumps(page)),1200)
        self.assertIn("Scene",page["text"])

    def test_no_tools_list_no_unsafely_assumed_schema(self):
        response=self._mcp([
            req(42,"tools/call",{"name":"get_scene_info","arguments":{}})
        ])
        self.assertEqual(response.returncode,0,response.stderr)
        data=json.loads(response.stdout)
        observed=data["result"]["content"][0]["text"]
        self.assertFalse(observed.startswith('{"pie_gateway"'))
        self.assertIn("Cube roughness",observed)

    def test_recovery_pages_exact_and_cross_project_isolation(self):
        content="REDUCED "+("x"*3200)
        reduced=reduce_text(self.root,content,surface="mcp",tool="safe",kind="api",
                            max_chars=800)
        offset=0
        assembled=[]
        while True:
            response=recovery_page(self.root,{"output_id":reduced["output_id"],
                                               "start":offset,"max_chars":900})
            data=json.loads(response["content"][0]["text"])
            assembled.append(data["text"])
            if data["next_start"] is None:
                break
            self.assertGreater(data["next_start"],offset)
            offset=data["next_start"]
        self.assertEqual("".join(assembled),content)
        elsewhere=self.base/"other-project"
        elsewhere.mkdir()
        (elsewhere/"pyproject.toml").write_text("[project]\nname='other'\n")
        with self.assertRaises(ValueError):
            recovery_page(elsewhere,{"output_id":reduced["output_id"]})

if __name__=="__main__":
    unittest.main()
