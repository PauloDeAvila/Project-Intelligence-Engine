"""End-to-end contract tests for the ONLY two supported PIE domains."""
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

from pie.gateway.domain import domain_route, register_codex, register_plan
from pie.gateway.web_results import web_result_eligible,web_snapshot_preview
from pie.retrieval.output_pipeline import recover_output


def request(id_,method,params=None):
    out={"jsonrpc":"2.0","id":id_,"method":method}
    if params is not None:out["params"]=params
    return out


SNAPSHOT=("### Page URL\nhttps://example.test/products?sort=popular\n"
          "### Page Title\nStore\n### Snapshot\n"
          "- main [ref=e1]:\n- heading \"Products\" [ref=e2]\n"+
          "".join(f'- link "Product {i}" [ref=e{i+10}]\n' for i in range(130)))


class WebReducerTests(unittest.TestCase):
    def test_recognizable_snapshot_only_and_fail_closed(self):
        self.assertTrue(web_result_eligible(SNAPSHOT,"browser_navigate"))
        self.assertTrue(web_result_eligible(SNAPSHOT,"browser_snapshot"))
        self.assertFalse(web_result_eligible(SNAPSHOT,"browser_take_screenshot"))
        self.assertFalse(web_result_eligible(SNAPSHOT,"browser_evaluate"))
        self.assertFalse(web_result_eligible(SNAPSHOT+"\n### Error\nNavigation failed","browser_navigate"))
        self.assertFalse(web_result_eligible(SNAPSHOT+"\nSet-Cookie: session=x","browser_navigate"))
        self.assertFalse(web_result_eligible(SNAPSHOT.replace("sort=popular","token=SECRET"),"browser_snapshot"))
        self.assertFalse(web_result_eligible(SNAPSHOT+'\n- textbox "Password" [ref=e900]',"browser_snapshot"))
        self.assertFalse(web_result_eligible("A"*4000,"browser_snapshot"))

    def test_actionable_refs_unmodified_but_preview_partial_and_untrusted(self):
        view=web_snapshot_preview(SNAPSHOT,700)
        self.assertIsNotNone(view)
        self.assertIn("ref=e2",view["preview"])
        self.assertEqual(view["page_origin"],"https://example.test")
        self.assertNotIn("?sort=popular",json.dumps(view))
        self.assertEqual(view["trust"],"UNTRUSTED_PAGE_DATA")
        self.assertFalse(view["safe_to_execute"])
        self.assertFalse(view["complete"])
        self.assertGreater(view["omitted_lines"],0)
        self.assertNotIn("ref=e139",view["preview"])


class DomainConfigTests(unittest.TestCase):
    def test_only_two_domains_without_guessing_unknown_servers(self):
        inner,allow,profile=domain_route("blender",["python","-m","blender"],python="py",max_chars=1200)
        self.assertEqual(inner[:3],["py","-m","pie.integrations.blender_mcp_bridge"])
        self.assertEqual(allow,())
        self.assertEqual(profile,"generic")
        direct,allowed,profile=domain_route("web",["npx","@playwright/mcp"],python="py",max_chars=1200)
        self.assertEqual(direct,["npx","@playwright/mcp"])
        self.assertIn("browser_navigate",allowed)
        self.assertIn("browser_snapshot",allowed)
        self.assertNotIn("browser_evaluate",allowed)
        self.assertEqual(profile,"web")
        with self.assertRaises(ValueError):
            domain_route("github",["node","server.js"],python="py",max_chars=1200)

    def test_codex_auditor_recognizes_only_explicit_domain_profiles(self):
        from pie.certification.coverage import audit_codex
        home=self._temp_codex_home()
        home.joinpath("config.toml").write_text(
            '[mcp_servers.pie_blender]\n'
            'command="python"\n'
            'args=["-m","pie.gateway.domain","serve","--domain","blender","--","uvx","mcp-for-blender"]\n'
            '[mcp_servers.pie_web]\n'
            'command="python"\n'
            'args=["-m","pie.gateway.domain","serve","--domain","web","--","npx","@playwright/mcp"]\n'
            '[mcp_servers.unprotected]\n'
            'command="node"\n'
            'args=["browser.js"]\n')
        audit=audit_codex(home)
        self.assertEqual(audit["mcp"]["wrapped_stdio"],2)
        self.assertEqual(audit["mcp"]["active_servers"],3)
        self.assertEqual(audit["mcp"]["unwrapped_or_unknown_servers"],["unprotected"])
        self.assertFalse(audit["universal_interception_certified"])

    def _temp_codex_home(self):
        import tempfile
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        return Path(folder.name)

    def test_register_plan_is_dry_run_and_never_overwrites(self):
        out=register_codex("web","pie-web",["node","server.js"],python="py")
        self.assertEqual(out["state"],"DRY_RUN")
        self.assertEqual(out["domain"],"web")
        args=register_plan("blender","pie-blender",["python","-m","blender"],python="py")
        self.assertIn("pie.gateway.domain",args)
        self.assertIn("serve",args)
        self.assertIn("--domain",args)
        with self.assertRaises(ValueError):
            register_plan("web","dangerous name",["node","server.js"],python="py")


class DomainStdioTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp=Path(temporary.name)
        self.root=self.tmp/"project"
        self.root.mkdir()
        (self.root/"pyproject.toml").write_text("[project]\nname='domain'\n")
        self.store=self.tmp/"store"
        self.patchenv=patch.dict(os.environ,{"PIE_GLOBAL_STORAGE_ROOT":str(self.store)})
        self.patchenv.start()
        self.addCleanup(self.patchenv.stop)
        self.env=dict(os.environ,
                      PIE_GLOBAL_STORAGE_ROOT=str(self.store),
                      PYTHONPATH=str(Path(__file__).resolve().parents[1]/"src"))

    def _run(self,domain,upstream,inputs,max_chars="1200",mark=None,env_extra=None):
        env=dict(self.env)
        if mark:env["PIE_TEST_DOMAIN_MARKER"]=str(mark)
        if env_extra:env.update(env_extra)
        cmd=[sys.executable,"-m","pie.gateway.domain","serve",
             "--domain",domain,"--max-chars",max_chars,
             "--workspace",str(self.root),"--store",str(self.store),
             "--",sys.executable,"-u","-c",upstream]
        proc=subprocess.run(cmd,input="\n".join(json.dumps(x) for x in inputs)+"\n",
                            text=True,env=env,capture_output=True,timeout=22)
        return proc

    def test_bootstrap_lifecycle_events_precede_mcp_events(self):
        upstream=r'''
import json,sys
for line in sys.stdin:
  q=json.loads(line)
  if "id" not in q: continue
  method=q.get("method")
  if method=="tools/list": result={"tools":[{"name":"get_scene_info","inputSchema":{"type":"object"}}]}
  elif method=="tools/call": result={"content":[{"type":"text","text":"scene"}]}
  else: result={"serverInfo":{"name":"mock","version":"1"},"protocolVersion":"2025-03-26","capabilities":{"tools":{}}}
  print(json.dumps({"jsonrpc":"2.0","id":q["id"],"result":result}),flush=True)
'''
        diagnostics=self.tmp/"bootstrap.jsonl"
        requests=[request(1,"initialize",{}),request(2,"tools/list",{}),
                  request(3,"tools/call",{"name":"get_scene_info","arguments":{}})]
        run=self._run("web",upstream,requests,
                      env_extra={"PIE_MCP_DIAGNOSTICS_PATH":str(diagnostics)})
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertTrue(diagnostics.is_file())
        events=[json.loads(line) for line in diagnostics.read_text().splitlines()]
        names=[item["event"] for item in events]
        self.assertIn("PROCESS_STARTED",names)
        self.assertIn("BOOTSTRAP_INITIALIZED",names)
        self.assertIn("IMPORT_SUCCEEDED",names)
        self.assertIn("UPSTREAM_STARTED",names)
        self.assertIn("MCP_INITIALIZE_RECEIVED",names)
        self.assertIn("MCP_TOOLS_LIST_RECEIVED",names)
        self.assertIn("MCP_TOOL_CALL_RECEIVED",names)
        self.assertIn("PROCESS_EXITING",names)
        self.assertNotIn("content",diagnostics.read_text())

    def test_web_navigation_is_called_once_and_recoverable(self):
        upstream=r"""
import json,os,sys
from pathlib import Path
snap="### Page URL\nhttps://example.test/products?sort=popular\n### Page Title\nStore\n### Snapshot\n- main [ref=e1]:\n- heading \"Products\" [ref=e2]\n"+"".join('- link "Product %d" [ref=e%d]\n'%(i,i+10) for i in range(130))
for line in sys.stdin:
  q=json.loads(line)
  if "id" not in q:continue
  method=q.get("method")
  if method=="tools/list":
    value={"tools":[{"name":name,"inputSchema":{"type":"object"}} for name in ("browser_navigate","browser_snapshot","browser_click","browser_take_screenshot","browser_evaluate","browser_get_struct")]}
  elif method=="tools/call":
    name=q["params"]["name"]
    m=os.environ.get("PIE_TEST_DOMAIN_MARKER")
    if m:
      p=Path(m)
      p.write_text(p.read_text()+"1" if p.exists() else "1")
    if name=="browser_navigate":value={"content":[{"type":"text","text":snap}]}
    elif name=="browser_click":value={"isError":True,"content":[{"type":"text","text":"Error: action failed"}]}
    elif name=="browser_take_screenshot":value={"content":[{"type":"image","data":"xyz","mimeType":"image/png"}]}
    elif name=="browser_evaluate":value={"content":[{"type":"text","text":"SECRET: do not compact this tool\n"*200}]}
    else:value={"content":[{"type":"text","text":"### Page URL\nhttps://example.test\n### Snapshot\n- button [ref=e9]\n"*90}],"structuredContent":{"status":"OK"}}
  else:value={"serverInfo":{"name":"mock-web","version":"1"},"protocolVersion":"2025-03-26","capabilities":{"tools":{}}}
  print(json.dumps({"jsonrpc":"2.0","id":q["id"],"result":value}),flush=True)
"""
        marker=self.tmp/"web_calls.txt"
        calls=[request(1,"initialize",{}),request(2,"tools/list",{}),
            request(3,"tools/call",{"name":"browser_navigate","arguments":{"url":"https://example.test"}}),
            request(4,"tools/call",{"name":"browser_click","arguments":{"ref":"e1"}}),
            request(5,"tools/call",{"name":"browser_take_screenshot","arguments":{}}),
            request(6,"tools/call",{"name":"browser_evaluate","arguments":{}}),
            request(7,"tools/call",{"name":"browser_get_struct","arguments":{}})]
        run=self._run("web",upstream,calls,mark=marker)
        self.assertEqual(run.returncode,0,run.stderr)
        responses={m["id"]:m for m in (json.loads(line) for line in run.stdout.splitlines())}
        self.assertEqual(set(responses),{1,2,3,4,5,6,7})
        self.assertEqual(marker.read_text(),"11111") # five tool calls, no duplicates
        tools=[x["name"] for x in responses[2]["result"]["tools"]]
        self.assertIn("pie_gateway_output_get",tools)
        reduced=json.loads(responses[3]["result"]["content"][0]["text"])
        self.assertEqual(reduced["state"],"PARTIAL")
        self.assertEqual(reduced["web"]["trust"],"UNTRUSTED_PAGE_DATA")
        self.assertFalse(reduced["web"]["safe_to_execute"])
        self.assertIn("ref=e2",reduced["preview"])
        self.assertNotIn("?sort=popular",reduced["preview"])
        recovered=recover_output(self.root,reduced["output_id"])
        self.assertIn("ref=e139",recovered["text"])
        self.assertIn("?sort=popular",recovered["text"])
        self.assertTrue(responses[4]["result"]["isError"])
        self.assertEqual(responses[5]["result"]["content"][0]["type"],"image")
        self.assertIn("SECRET:",responses[6]["result"]["content"][0]["text"])
        self.assertEqual(responses[7]["result"]["structuredContent"]["status"],"OK")

    def test_blender_bridge_tools_and_write_outputs_are_preserved(self):
        upstream=r"""
import json,sys,os
from pathlib import Path
for line in sys.stdin:
  q=json.loads(line)
  if "id" not in q:continue
  m=q.get("method")
  if m=="tools/list":
    v={"tools":[{"name":n,"inputSchema":{"type":"object"}} for n in ("get_scene_info","get_object_info","execute_blender_code")]}
  elif m=="tools/call":
    name=q["params"]["name"]
    marker=os.environ.get("PIE_TEST_DOMAIN_MARKER")
    if marker:
      p=Path(marker);p.write_text(p.read_text()+"1" if p.exists() else "1")
    value=("Object Cube material Metallic\n"*250) if name=="get_scene_info" else "MATERIAL_EDITED"
    v={"content":[{"type":"text","text":value}]}
  else:v={"serverInfo":{"name":"mock-blender","version":"1"},"protocolVersion":"2025-03-26","capabilities":{"tools":{}}}
  print(json.dumps({"jsonrpc":"2.0","id":q["id"],"result":v}),flush=True)
"""
        marker=self.tmp/"blender_calls.txt"
        reqs=[request(1,"initialize",{}),request(2,"tools/list",{}),
              request(3,"tools/call",{"name":"get_scene_info","arguments":{}}),
              request(4,"tools/call",{"name":"execute_blender_code","arguments":{"code":"print(1)"}})]
        p=self._run("blender",upstream,reqs,mark=marker)
        self.assertEqual(p.returncode,0,p.stderr)
        results={x["id"]:x for x in (json.loads(line) for line in p.stdout.splitlines())}
        self.assertEqual(marker.read_text(),"11")
        names={x["name"] for x in results[2]["result"]["tools"]}
        self.assertTrue({"pie_blender_expand","pie_blender_scene_delta","pie_gateway_output_get"}.issubset(names))
        snapshot=json.loads(results[3]["result"]["content"][0]["text"])
        self.assertEqual(snapshot["status"],"PARTIAL")
        self.assertEqual(results[4]["result"]["content"][0]["text"],"MATERIAL_EDITED")

if __name__=="__main__":
    unittest.main()
