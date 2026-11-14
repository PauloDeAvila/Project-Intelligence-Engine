"""Synthetic accounting tests: validate schema logic, NOT live provider token savings."""
from __future__ import annotations
import json,sys,tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from pie.certification.live_codex import SCHEMA,parse_codex_jsonl,compare,validate_scenario,preflight_codex
from pie.certification.coverage import audit_codex

def event(inp=1200,cached=100,out=200,answer="answer"):
    objects=[{"type":"thread.started","thread_id":"opaque"},
             {"type":"item.started","item":{"type":"mcp_tool_call"}},
             {"type":"item.completed","item":{"type":"mcp_tool_call","server":"pie-web-optimized","tool":"browser_snapshot","status":"completed"}},
             {"type":"item.completed","item":{"type":"agent_message","text":answer}},
             {"type":"turn.completed","usage":{"input_tokens":inp,
               "cached_input_tokens":cached,"output_tokens":out,"reasoning_output_tokens":0}}]
    return "\n".join(json.dumps(x) for x in objects)+"\n"

def row(rep,arm,inp,*,passed=True,config="a"):
    return {"schema":SCHEMA,"condition":arm,"scenario_id":"one","repetition":rep,
            "model":"test-model","codex_version":"codex-test-1",
            "prompt_sha256":"prompt-hash","expected_sha256":"expected-hash",
            "workspace_commit":"0"*40,"configuration_sha256":config,
            "oracle_kind":"exact_text","oracle_pass":passed,
            "runtime_ms":30.0,"tool_events":2,"source":"codex_exec_json_turn_completed",
            "provider_reported":True,
            "usage":{"input_tokens":inp,"cached_input_tokens":100,
                     "output_tokens":50,"reasoning_output_tokens":0}}

class UsageTests(unittest.TestCase):
    def test_provider_usage_extracted(self):
        actual=parse_codex_jsonl(event())
        self.assertEqual(actual["usage"]["input_tokens"],1200)
        self.assertEqual(actual["usage"]["cached_input_tokens"],100)
        self.assertEqual(actual["usage"]["output_tokens"],200)
        self.assertEqual(actual["answer"],"answer")
        self.assertEqual(actual["tool_events"],1)
        self.assertTrue(actual["provider_reported"])
        self.assertEqual(actual["mcp_tools"], [{"server":"pie-web-optimized","tool":"browser_snapshot","status":"completed"}])
    def test_missing_conflicting_or_failed_usage_rejected(self):
        base=event()
        bad=("","not json",'{"type":"turn.completed"}',base+base,
             base+'{"type":"turn.failed"}',
             base.replace('"input_tokens": 1200','"input_tokens": -1'),
             base.replace('"cached_input_tokens": 100','"cached_input_tokens": 9999'))
        for trace in bad:
            with self.subTest(trace=trace[:15]):
                with self.assertRaises(ValueError):parse_codex_jsonl(trace)
    def test_scenario_requires_exact_oracle_and_real_model(self):
        with self.assertRaises(ValueError):
            validate_scenario({"scenario_id":"one","prompt":"x","model":"test"})
        with self.assertRaises(ValueError):
            validate_scenario({"scenario_id":"one","prompt":"x","model":"MODEL_ID_CONFIGURE_BEFORE_USE","expected_exact":"x"})
    def test_paired_usage_and_supplied_price_estimate(self):
        a=[]
        for i in range(1,4):a.extend((row(i,"baseline",1500,config="a"),row(i,"optimized",500,config="b")))
        r=compare(a,min_pairs=3,prices={"input_per_million":1.0,
                  "cached_input_per_million":0.5,"output_per_million":3.0})
        self.assertEqual(r["state"],"REAL_PROVIDER_TOKENS_COMPARED")
        self.assertEqual(r["pairs"],3)
        self.assertEqual(r["savings_percent"],66.667)
        self.assertEqual(r["totals"]["baseline"]["input_tokens"],4500)
        self.assertEqual(r["totals"]["optimized"]["cached_input_tokens"],300)
        self.assertIsNotNone(r["estimated_usd"])
    def test_fail_closed_on_unpaired_same_config_incorrect_or_tool_free(self):
        a=[row(1,"baseline",1000),row(1,"optimized",500)]
        self.assertEqual(compare(a,min_pairs=1)["state"],"NOT_CERTIFIED")
        a[1]["configuration_sha256"]="other"
        self.assertEqual(compare(a,min_pairs=3)["state"],"NOT_CERTIFIED")
        a[1]["oracle_pass"]=False
        self.assertEqual(compare(a,min_pairs=1)["state"],"NOT_CERTIFIED")
        a[1]["oracle_pass"]=True;a[1]["tool_events"]=0
        self.assertEqual(compare(a,min_pairs=1)["state"],"NOT_CERTIFIED")
        a[1]["tool_events"]=2;a[1]["provider_reported"]=False
        self.assertEqual(compare(a,min_pairs=1)["state"],"NOT_CERTIFIED")
        a[1]["provider_reported"]=True
        self.assertEqual(compare(a+[a[0]],min_pairs=1)["state"],"NOT_CERTIFIED")

class CoverageTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.home=Path(tmp.name)
    def test_stdio_mcp_http_and_terminal_hook_gaps_are_visible(self):
        (self.home/"config.toml").write_text('''
[mcp_servers.direct]
command = "npx"
args = ["server"]
[mcp_servers.wrapped]
command = "python"
args = ["-m", "pie.gateway.mcp_stdio", "--", "python", "server.py"]
[mcp_servers.remote]
url = "https://example.invalid/mcp"
''')
        (self.home/"hooks.json").write_text(json.dumps({"hooks":[{"command":"rtk hook codex","matcher":"Bash"}]}))
        with patch("pie.certification.coverage.shutil.which",return_value="/usr/bin/rtk"):
            output=audit_codex(self.home)
        self.assertTrue(output["rtk_hook_configured"])
        self.assertEqual(output["mcp"]["active_servers"],3)
        self.assertEqual(output["mcp"]["wrapped_stdio"],1)
        self.assertEqual(output["mcp"]["unwrapped_or_unknown_servers"],["direct","remote"])
        self.assertFalse(output["universal_interception_certified"])
        self.assertNotIn("server.py",json.dumps(output))
    def test_missing_rtk_hook_never_claims_interception(self):
        (self.home/"config.toml").write_text("[mcp_servers.a]\ncommand='python'\n")
        with patch("pie.certification.coverage.shutil.which",return_value=None):
            audit=audit_codex(self.home)
        self.assertEqual(audit["terminal_interception"],"NOT_VERIFIED")
        self.assertEqual(audit["coverage_state"],"GAPS_OR_NO_ROUTED_SERVERS")

class PreflightTests(unittest.TestCase):
    def test_missing_auth_blocks_before_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"; root.mkdir()
            subprocess.run(["git","init","-q"],cwd=root,check=True)
            (root/"README.md").write_text("fixture")
            subprocess.run(["git","add","."],cwd=root,check=True)
            subprocess.run(["git","-c","user.email=test@example.invalid","-c","user.name=test","commit","-qm","fixture"],cwd=root,check=True)
            home=Path(tmp)/"home"; home.mkdir()
            (home/"config.toml").write_text('model="gpt-5.6-luna"\n[mcp_servers.blender]\ncommand="blender"\n')
            scenario={"scenario_id":"x","prompt":"inspect","expected_exact":"x","model":"gpt-5.6-luna","description":"x","required_mcp_server":"blender"}
            with patch("pie.certification.live_codex.shutil.which",return_value="codex"):
                result=preflight_codex(scenario,condition="baseline",workspace=root,codex_home=home)
            self.assertEqual(result["state"],"BLOCKED")
            self.assertIn("PRECHECK_AUTH_MISSING",result["errors"])

    def test_profile_is_validated_without_reading_auth_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"; root.mkdir()
            subprocess.run(["git","init","-q"],cwd=root,check=True)
            (root/"README.md").write_text("fixture")
            subprocess.run(["git","add","."],cwd=root,check=True)
            subprocess.run(["git","-c","user.email=test@example.invalid","-c","user.name=test","commit","-qm","fixture"],cwd=root,check=True)
            home=Path(tmp)/"home"; home.mkdir()
            (home/"config.toml").write_text('model="gpt-5.6-luna"\n')
            (home/"probe.config.toml").write_text('model_reasoning_effort="medium"\n')
            scenario={"scenario_id":"x","prompt":"inspect","expected_exact":"x","model":"gpt-5.6-luna","description":"x"}
            with patch("pie.certification.live_codex.shutil.which",return_value="codex"):
                result=preflight_codex(scenario,condition="baseline",workspace=root,codex_home=home,profile="probe")
            self.assertEqual(result["checks"]["profile"],"PASS")
            self.assertIn("PRECHECK_AUTH_MISSING",result["errors"])

if __name__=="__main__":unittest.main()
