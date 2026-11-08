"""Regression tests for OpenCode's documented async completion contract."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from pie.orchestrator.opencode import OpenCodeHttpAdapter
from pie.orchestrator.service import Orchestrator, ProjectPolicy
from pie.orchestrator.store import TaskStore
from pie.orchestrator.models import TaskStatus


class Fresh:
    def validate(self, project):
        return {"index_state":"CURRENT"}


class FakeOpenCode(OpenCodeHttpAdapter):
    def __init__(self, responses):
        super().__init__("http://127.0.0.1:4096","test-only")
        self.responses=iter(responses)
        self.calls=[]

    def _request(self,method,path,body=None,directory=None):
        self.calls.append((method,path,body,directory))
        if path=="/mcp":
            return {"pie":{"status":"connected"}}
        result=next(self.responses)
        if isinstance(result,Exception):
            raise result
        if method=="POST" and path=="/session" and isinstance(result,dict):
            return {**result,"directory":str(directory)}
        return result


class OpenCodeCompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name).resolve()
        self.store=TaskStore(root/"state.sqlite3")
        self.addCleanup(self.store.close)
        self.project=ProjectPolicy("pie",root,frozenset({"opencode/nemotron-3.5-lightning-free"}))
        self.request={"project_id":"pie","task_type":"read_only_review",
                      "model":"opencode/nemotron-3.5-lightning-free","idempotency_key":"one"}

    def make(self, adapter):
        service=Orchestrator(self.store,{"pie":self.project},adapter,Fresh())
        task,_=service.submit("client",self.request)
        return service,task

    def test_completed_with_204_busy_then_finished_assistant(self):
        adapter=FakeOpenCode([
            {"id":"ses_new"},None,
            {"ses_new":{"type":"busy"}},
            {"ses_new":{"type":"idle"}},
            [{"info":{"role":"user","id":"usr"}},{"info":{"role":"assistant","id":"a1",
                  "finish":"stop","tokens":{"input":19,"output":4}},"parts":[{"type":"text","text":"internal"},
                  {"type":"tool","tool":"pie_project_status","callID":"call_pie_1",
                   "state":{"status":"completed","output":"CURRENT"}}]}],
        ])
        service,task=self.make(adapter)
        with patch("pie.orchestrator.opencode.time.sleep"):
            result=service.run(task.id)
        self.assertEqual(result.status,TaskStatus.COMPLETED)
        self.assertEqual(result.session_id,"ses_new")
        self.assertEqual(result.metrics,{"input":19,"output":4})
        self.assertNotIn("internal",json.dumps(result.result))
        self.assertEqual(result.result["pie_mcp_evidence"][0]["tool"], "pie_project_status")
        self.assertEqual(len(result.result["pie_mcp_evidence"][0]["output_sha256"]), 64)
        self.assertEqual(result.result["index_validation"]["index_state"], "CURRENT")
        self.assertIn("session_bound",[event["kind"] for event in self.store.events(task.id)])
        self.assertEqual(adapter.calls[2][1],"/session/ses_new/prompt_async")
        self.assertEqual(adapter.calls[2][2]["tools"]["bash"],False)
        self.assertEqual(adapter.calls[0][1],"/mcp")
        self.assertEqual(adapter.calls[1][3],self.project.root)
        self.assertEqual(adapter.calls[2][3],self.project.root)
        self.assertIn(("GET","/session/status",None,self.project.root),adapter.calls)

    def test_no_false_completion_without_assistant(self):
        self.assertFalse(OpenCodeHttpAdapter._finished([{'info':{'role':'user'}}])[0])
        self.assertFalse(OpenCodeHttpAdapter._finished([{'info':{'role':'assistant','finish':None}}])[0])

    def test_truncated_assistant_is_not_certified(self):
        with self.assertRaisesRegex(RuntimeError,"did not finish normally"):
            OpenCodeHttpAdapter._finished([{"info":{"role":"assistant","finish":"length"}}])

    def test_session_binding_precedes_model_failure(self):
        adapter=FakeOpenCode([{"id":"ses_bound"},RuntimeError("remote prompt failed")])
        service,task=self.make(adapter)
        end=service.run(task.id)
        self.assertEqual(end.status,TaskStatus.FAILED)
        self.assertEqual(end.session_id,"ses_bound")
        self.assertNotIn("remote prompt failed",str(end.error))

    def test_model_finish_without_pie_tool_is_not_a_certified_completion(self):
        adapter=FakeOpenCode([{"id":"ses_bound"},None,{},[{"info":{"role":"assistant","finish":"stop"},
                                                            "parts":[{"type":"text","text":"PIE CURRENT"}]}]])
        service,task=self.make(adapter)
        end=service.run(task.id)
        self.assertEqual(end.status,TaskStatus.FAILED)
        self.assertEqual(end.session_id,"ses_bound")
        self.assertIsNone(end.result)

    def test_non_pie_mcp_tool_is_not_proof(self):
        with self.assertRaisesRegex(RuntimeError, "No completed PIE MCP"):
            OpenCodeHttpAdapter._finished([{"info":{"role":"assistant","finish":"stop"},
                "parts":[{"type":"tool","tool":"doctor_mesh_status",
                          "state":{"status":"completed","output":"CURRENT"}}]}])

    def test_errored_pie_tool_is_not_proof(self):
        with self.assertRaisesRegex(RuntimeError, "No completed PIE MCP"):
            OpenCodeHttpAdapter._finished([{"info":{"role":"assistant","finish":"stop"},
                "parts":[{"type":"tool","tool":"pie_project_status",
                          "state":{"status":"error","output":"failed"}}]}])

    def test_session_binding_cannot_change(self):
        adapter=FakeOpenCode([{"id":"ses_bound"},None,{},[{"info":{"role":"assistant","finish":"stop"},"parts":[{"type":"tool","tool":"pie_project_status","state":{"status":"completed","output":"CURRENT"}}]}]])
        service,task=self.make(adapter)
        end=service.run(task.id)
        self.assertEqual(end.status,TaskStatus.COMPLETED)
        with self.assertRaises(ValueError):
            self.store.bind_session(task.id,"another")


if __name__=="__main__":
    unittest.main()
