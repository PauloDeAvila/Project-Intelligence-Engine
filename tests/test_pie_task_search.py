"""Stage 2 retrieval verification: FTS5, upgrade, boundaries, MCP and CLI."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "src"))
from pie.interfaces.cli import main
from pie.interfaces.mcp_server import dispatch,TOOLS
from pie.retrieval.task_memory import start_task,record_task
from pie.retrieval.task_search import search_tasks
from pie.storage.database import connect


class TaskSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        db=connect(self.root / ".pie" / "index.sqlite3")
        db.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_upgrade_existing_memory_and_incremental_events(self):
        a=start_task(self.root,"Corrigir login quebrado")["task_id"]
        record_task(self.root,a,"decision","Preservar autenticação pública",
                    "src/auth.py:12")
        found=search_tasks(self.root,"autenticação")
        self.assertEqual(found["state"],"FOUND")
        self.assertEqual(found["matches"][0]["task_id"],a)
        self.assertEqual(found["matches"][0]["reference"],"src/auth.py:12")
        self.assertEqual(found["matches"][0]["verification"],"agent_supplied_unverified")
        record_task(self.root,a,"checkpoint","Validar regressão após correção")
        again=search_tasks(self.root,"regressão")
        self.assertEqual(again["state"],"FOUND")
        self.assertEqual(again["matches"][0]["kind"],"checkpoint")
        self.assertIsInstance(again["matches"][0]["event_id"],int)

    def test_persists_between_connections(self):
        a=start_task(self.root,"Analyze dependency graph")["task_id"]
        self.assertEqual(search_tasks(self.root,"dependency")["matches"][0]["task_id"],a)
        record_task(self.root,a,"result","Indexed symbols in SQLite")
        self.assertEqual(search_tasks(self.root,"SQLite")["matches"][0]["task_id"],a)

    def test_no_cross_project_leakage(self):
        start_task(self.root,"Sensitive local objective")
        with tempfile.TemporaryDirectory() as tmp:
            other=Path(tmp)
            connect(other / ".pie" / "index.sqlite3").close()
            self.assertEqual(search_tasks(other,"Sensitive")["state"],"NOT_FOUND")

    def test_search_operators_are_inert(self):
        a=start_task(self.root,"Fix login")["task_id"]
        for q in ('login OR NOT *', 'login" OR "anything',
                  'task_id:login', "login; DROP TABLE pie_tasks;"):
            result=search_tasks(self.root,q)
            self.assertEqual(result["verification"],"agent_supplied_unverified")
        self.assertEqual(search_tasks(self.root,"login")["matches"][0]["task_id"],a)

    def test_empty_stopwords_and_invalid_arguments(self):
        self.assertEqual(search_tasks(self.root,"o que eu")["state"],"NO_SEARCH_TERMS")
        for q in (""," ","x"*1025,"\x00"):
            with self.assertRaises(ValueError):search_tasks(self.root,q)
        for limit in (0,21,True):
            with self.assertRaises(ValueError):search_tasks(self.root,"login",limit=limit)
        with self.assertRaises(ValueError):search_tasks(self.root,"login",max_chars=1)

    def test_hard_result_budget_keeps_full_or_omits(self):
        a=start_task(self.root,"Huge context checkpoint")["task_id"]
        record_task(self.root,a,"note","checkpoint "+"z"*3900+"important negation")
        found=search_tasks(self.root,"checkpoint",max_chars=1000,limit=10)
        self.assertLessEqual(len(json.dumps(found,ensure_ascii=False,separators=(",",":"))),1000)
        self.assertGreaterEqual(found["omitted"],1)
        self.assertFalse(any(m["text"].endswith("important") for m in found["matches"]))

    def test_fallback_matches_with_no_fts(self):
        a=start_task(self.root,"Review gateway auth")["task_id"]
        with patch("pie.retrieval.task_search._ensure_fts", return_value=False):
            result=search_tasks(self.root,"gateway")
        self.assertEqual(result["backend"],"lexical_fallback")
        self.assertEqual(result["matches"][0]["task_id"],a)

    def test_cli_and_mcp(self):
        task=start_task(self.root,"Investigate incremental indexing")["task_id"]
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["task-search","indexing","--root",str(self.root)]),0)
        self.assertEqual(json.loads(output.getvalue())["matches"][0]["task_id"],task)
        self.assertIn("pie_task_search",{t["name"] for t in TOOLS})
        req={"jsonrpc":"2.0","id":7,"method":"tools/call",
             "params":{"name":"pie_task_search","arguments":{"query":"incremental"}}}
        answer=dispatch(req,self.root)
        self.assertEqual(json.loads(answer["result"]["content"][0]["text"])["matches"][0]["task_id"],task)
        req["params"]["arguments"]["limit"]=25
        self.assertTrue(dispatch(req,self.root)["result"]["isError"])


if __name__=="__main__":
    unittest.main()
