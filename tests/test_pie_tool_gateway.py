"""PIE gateway contract tests: allowlist, budgets, recovery and MCP."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from pie.storage.database import connect
from pie.retrieval.task_memory import start_task,record_task
from pie.interfaces.tool_gateway import execute_gateway
from pie.interfaces.mcp_server import dispatch,TOOLS

class ToolGatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        connect(self.root/".pie"/"index.sqlite3").close()
    def tearDown(self):
        self.tmp.cleanup()
    def test_task_memory_routed_and_persisted(self):
        tid=start_task(self.root,"Repair login")["task_id"]
        record_task(self.root,tid,"checkpoint","Check auth regression")
        x=execute_gateway(self.root,"task_search",{"query":"regression"})
        self.assertEqual(x["operation"],"task_search")
        self.assertEqual(x["state"],"COMPLETE")
        self.assertEqual(json.loads(x["result"])["matches"][0]["task_id"],tid)
        self.assertEqual(x["telemetry"]["measurement"],"characters_not_tokens")
        restored=execute_gateway(self.root,"output_get",{"output_id":x["telemetry"]["output_id"]})
        self.assertEqual(restored["result"]["text"],x["result"])
    def test_context_budget_withholds_entire_content(self):
        tid=start_task(self.root,"Huge backlog")["task_id"]
        record_task(self.root,tid,"checkpoint","sentinel "+"x"*3900)
        x=execute_gateway(self.root,"task_resume",{"task_id":tid},max_chars=512)
        self.assertEqual(x["state"],"PARTIAL")
        self.assertIsNone(x["result"])
        self.assertEqual(x["telemetry"]["measurement"],"characters_not_tokens")
        restored=execute_gateway(self.root,"output_get",{"output_id":x["telemetry"]["output_id"]})
        self.assertIn("sentinel",restored["result"]["text"])
        self.assertEqual(x["telemetry"]["sha256"],restored["result"]["sha256"])
    def test_no_arbitrary_shell_or_unknown_arguments(self):
        for op in ("shell","exec","run","read_any_file","__import__"):
            with self.assertRaises(ValueError):
                execute_gateway(self.root,op,{})
        with self.assertRaises(ValueError):
            execute_gateway(self.root,"task_resume",{"path":"../../etc/passwd"})
        with self.assertRaises(ValueError):
            execute_gateway(self.root,"task_search",{"query":"x","limit":True})
        with self.assertRaises(ValueError):
            execute_gateway(self.root,"task_search",{"query":"x","limit":21})
        with self.assertRaises(ValueError):
            execute_gateway(self.root,"source_query",{"query":"x","mode":"execute"})
        with self.assertRaises(ValueError):
            execute_gateway(self.root,"task_resume",max_chars=10)
    def test_project_isolation(self):
        x=execute_gateway(self.root,"project_status")
        with tempfile.TemporaryDirectory() as other:
            root=Path(other);connect(root/".pie"/"index.sqlite3").close()
            with self.assertRaises(ValueError):
                execute_gateway(root,"output_get",{"output_id":x["telemetry"]["output_id"]})
    def test_compact_and_status_from_gateway(self):
        x=execute_gateway(self.root,"output_compact",{"text":"error\nerror\nok","kind":"test","exit_code":1})
        self.assertEqual(x["result"]["exit_code"],1)
        self.assertEqual(x["result"]["state"],"COMPLETE")
        self.assertIn("[x2]",x["result"]["text"])
        y=execute_gateway(self.root,"project_status")
        self.assertEqual(json.loads(y["result"])["files"],0)
    def test_mcp_contract_and_validation(self):
        self.assertIn("pie_tool_gateway",{t["name"] for t in TOOLS})
        def call(arguments):
            r=dispatch({"jsonrpc":"2.0","id":1,"method":"tools/call",
                        "params":{"name":"pie_tool_gateway","arguments":arguments}},self.root)
            return r["result"]
        r=call({"operation":"project_status","max_chars":1000})
        value=json.loads(r["content"][0]["text"])
        self.assertEqual(value["operation"],"project_status")
        self.assertFalse(r.get("isError",False))
        for args in (
            {"operation":"arbitrary_command"},
            {"operation":"task_search","arguments":{"query":"x","unknown":1}},
            {"operation":"project_status","max_chars":True},
            {"operation":"output_compact","arguments":{"text":"safe","kind":"evil"}}
        ):
            self.assertTrue(call(args)["isError"])

if __name__=="__main__":
    unittest.main()
