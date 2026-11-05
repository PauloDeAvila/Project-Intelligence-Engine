"""RTK-style output adapter: deterministic compaction and safe recovery."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from pie.interfaces.cli import main
from pie.interfaces.mcp_server import dispatch,TOOLS
from pie.retrieval.output_pipeline import compact_output,recover_output
from pie.storage.database import connect

class OutputPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        connect(self.root/".pie"/"index.sqlite3").close()
    def tearDown(self):
        self.tmp.cleanup()
    def test_repeated_lines_and_failure_first(self):
        s="ok\nok\nFAIL auth denied\n"
        x=compact_output(self.root,s,kind="test")
        self.assertEqual(x["state"],"COMPLETE")
        self.assertTrue(x["text"].startswith("FAIL auth denied"))
        self.assertIn("ok [x2]",x["text"])
        self.assertEqual(x["exit_code"],None)
        y=recover_output(self.root,x["output_id"])
        self.assertEqual(y["text"],s)
        self.assertEqual(y["sha256"],hashlib.sha256(s.encode()).hexdigest())
    def test_partial_recover_and_error_status(self):
        s="\n".join("ERROR "+str(i)+" "+("a"*100) for i in range(30))
        x=compact_output(self.root,s,max_chars=300,exit_code=2)
        self.assertEqual(x["state"],"PARTIAL")
        self.assertGreater(x["omitted_unique_lines"],0)
        self.assertEqual(x["exit_code"],2)
        self.assertEqual(recover_output(self.root,x["output_id"])["text"],s)
    def test_redacts_before_storing(self):
        s="Authorization: Bearer abcdefgh0123\ntoken=secret123456\n"
        x=compact_output(self.root,s)
        y=recover_output(self.root,x["output_id"])
        self.assertNotIn("abcdef",y["text"])
        self.assertNotIn("secret123456",y["text"])
        self.assertIn("[REDACTED]",y["text"])
        self.assertTrue(x["sanitized_recovery"])
    def test_project_isolation_and_invalid_inputs(self):
        x=compact_output(self.root,"test")
        with tempfile.TemporaryDirectory() as tmp:
            other=Path(tmp);connect(other/".pie"/"index.sqlite3").close()
            with self.assertRaises(ValueError):
                recover_output(other,x["output_id"])
        for kw in ({"kind":"invalid"},{"max_chars":12},{"exit_code":True}):
            with self.assertRaises(ValueError):
                compact_output(self.root,"text",**kw)
        for bad in ("../abc","a"*32):
            with self.assertRaises(ValueError):recover_output(self.root,bad)
        with self.assertRaises(ValueError):compact_output(self.root,"a"*500001)
    def test_cli_and_mcp(self):
        f=self.root/"run.txt";f.write_text("failed\nfailed\nok",encoding="utf-8")
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["output-compact","--file",str(f),"--kind","test",
                                   "--root",str(self.root)]),0)
        d=json.loads(out.getvalue());self.assertEqual(d["kind"],"test")
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["output-get","--output-id",d["output_id"],
                                   "--root",str(self.root)]),0)
        self.assertIn("failed\nfailed",json.loads(out.getvalue())["text"])
        self.assertIn("pie_output_compact",{t["name"] for t in TOOLS})
        def call(name,args):
            return dispatch({"jsonrpc":"2.0","id":1,"method":"tools/call",
                             "params":{"name":name,"arguments":args}},self.root)["result"]
        x=json.loads(call("pie_output_compact",{"text":"error\nerror","exit_code":1})["content"][0]["text"])
        self.assertEqual(x["exit_code"],1)
        restored=json.loads(call("pie_output_get",{"output_id":x["output_id"]})["content"][0]["text"])
        self.assertEqual(restored["text"],"error\nerror")
        self.assertTrue(call("pie_output_compact",{"text":"hi","kind":"unknown"})["isError"])
        self.assertTrue(call("pie_output_get",{"output_id":"bad"})["isError"])

if __name__=="__main__":unittest.main()
