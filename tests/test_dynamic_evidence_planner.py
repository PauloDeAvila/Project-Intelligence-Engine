"""Thirty independent task formulations with expert-authored field requirements.

IMPORTANT: This is deterministic *planner* coverage, not proof a Qwen model
understands these questions. The gold keys are written independently here,
and never included in the dynamic model prompt.
"""
from __future__ import annotations

import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
import threading
import tempfile
import unittest

from pie.indexing.indexer import index_project
from pie.interfaces.cli import command_init
from pie.interfaces.gateway import Gateway
from pie.retrieval.evidence import build_evidence
from pie.retrieval.dynamic_selection import (
    FIELD_ORDER, FIELDS, plan_evidence, selection_prompt,
    validate_dynamic_selection, selection_json_schema,
)

# Manually reviewed examples with more than one intended selection.
# Expected fields do NOT go to the model. Separate safety-abstention scenarios
# are not counted as successful positive information retrieval.
CASES = [
    ("location", "Onde analyze_mesh está definida?", ["path", "line"]),
    ("location", "Em qual arquivo analyze_mesh está definida?", ["path", "line"]),
    ("location", "Where is analyze_mesh defined?", ["path", "line"]),
    ("location", "Qual linha contém analyze_mesh?", ["line"]),
    ("location", "Qual é a localização de analyze_mesh?", ["path", "line"]),
    ("signature", "Qual é a assinatura de analyze_mesh?", ["signature"]),
    ("signature", "Quais parâmetros analyze_mesh recebe?", ["signature"]),
    ("signature", "Show the signature of analyze_mesh", ["signature"]),
    ("signature", "Quais argumentos analyze_mesh declara?", ["signature"]),
    ("signature", "Qual parametro analyze_mesh declara?", ["signature"]),
    ("callers", "Quantas chamadas diretas existem para analyze_mesh?", ["direct_call_count"]),
    ("callers", "Qual a quantidade de chamadas de analyze_mesh?", ["direct_call_count"]),
    ("callers", "How many calls refer to analyze_mesh?", ["direct_call_count"]),
    ("callers", "Quem chama analyze_mesh?", ["direct_call_sites"]),
    ("callers", "Quais consumidores chamam analyze_mesh?", ["direct_call_sites"]),
    ("combined", "Onde analyze_mesh está definida e qual sua assinatura?",
     ["signature", "path", "line"]),
    ("combined", "Em qual arquivo e linha analyze_mesh está definida e quais parâmetros aceita?",
     ["signature", "path", "line"]),
    ("combined", "Qual assinatura e quantas chamadas de analyze_mesh?",
     ["signature", "direct_call_count"]),
    ("combined", "Quem chama analyze_mesh e qual sua assinatura?",
     ["signature", "direct_call_sites"]),
    ("combined", "Quantas chamadas e quais consumidores chamam analyze_mesh?",
     ["direct_call_count", "direct_call_sites"]),
    ("impact", "Se eu alterar analyze_mesh, o que quebra?", None),
    ("impact", "Qual impacto de mudar analyze_mesh?", None),
    ("impact", "Posso garantir que mudar analyze_mesh é seguro?", None),
    ("impact", "Will changing analyze_mesh break callers?", None),
    ("impact", "Analyze the runtime impact of analyze_mesh", None),
    ("unsupported", "Explique a arquitetura geral de analyze_mesh", None),
    ("unsupported", "O código de analyze_mesh é eficiente?", None),
    ("unsupported", "Qual o algoritmo usado pela função?", None),
    ("unsupported", "What does analyze_mesh actually compute?", None),
    ("unsupported", "Qual a complexidade temporal de analyze_mesh?", None),
]


class IndependentPlannerGoldTests(unittest.TestCase):
    def test_30_gold_cases(self):
        self.assertEqual(len(CASES), 30)
        for category, question, expected in CASES:
            with self.subTest(category=category, question=question):
                result = plan_evidence(question)
                if expected is None:
                    self.assertEqual(result["status"], "ABSTAIN", result)
                else:
                    self.assertEqual(result["status"], "PLANNED", result)
                    self.assertEqual(result["required_fields"], expected)

    def test_schema_is_structural_and_never_contains_gold(self):
        schema = selection_json_schema()["json_schema"]["schema"]
        self.assertEqual(schema["required"], ["selected_fields"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["selected_fields"]["items"]["enum"], list(FIELD_ORDER))
        self.assertNotIn("path", schema.get("required", []))
        self.assertNotIn("evidence_id", schema["properties"])

    def test_invalid_shape_reports_keys_without_exposing_values(self):
        ev = {"evidence_id": "pie:one", "signature": "def f():",
              "path": "geometry.py", "line": 1, "direct_call_count": 0,
              "direct_call_sites": []}
        result = validate_dynamic_selection(ev, {
            "selected_fields": ["path", "line"], "evidence_id": "secret-hash"},
            plan_evidence("Onde analyze_mesh está definida?"))
        self.assertEqual(result["reason"], "invalid_selection_shape")
        self.assertEqual(result["received_keys"], ["evidence_id", "selected_fields"])
        self.assertNotIn("secret-hash", str(result))

    def test_dynamic_prompt_does_not_leak_plan_or_answer_values(self):
        question = "Onde analyze_mesh está definida?"
        prompt = selection_prompt(question, "pie:identifier")
        self.assertIn("selected_fields", prompt)
        self.assertIn(question, prompt)
        self.assertNotIn("pie:identifier", prompt)
        self.assertNotIn("EVIDENCE_ID", prompt)
        self.assertIn("CATALOG=", prompt)
        self.assertNotIn("EXPECTED_OUTPUT", prompt)
        self.assertNotIn("geometry.py", prompt)
        self.assertNotIn("def analyze_mesh(", prompt)

    def test_model_selection_is_checked_against_independent_required_fields(self):
        ev = {"evidence_id": "pie:one", "signature": "def f():",
              "path": "geometry.py", "line": 1, "direct_call_count": 0,
              "direct_call_sites": []}
        plan = plan_evidence("Onde analyze_mesh está definida?")
        valid = validate_dynamic_selection(ev, {
            "selected_fields": ["path", "line"]}, plan)
        self.assertEqual(valid["status"], "VERIFIED")
        wrong = validate_dynamic_selection(ev, {
            "selected_fields": ["signature"]}, plan)
        self.assertEqual(wrong["status"], "REJECTED")
        self.assertEqual(wrong["missing_required"], ["path", "line"])
        self.assertEqual(wrong["unexpected_fields"], ["signature"])

    def test_schema_rejects_invented_ids_and_duplicate_fields(self):
        ev = {"evidence_id": "pie:one", "signature": "def f():",
              "path": "geometry.py", "line": 1, "direct_call_count": 0,
              "direct_call_sites": []}
        plan = plan_evidence("Qual é a assinatura?")
        bad = [
            ({"evidence_id": "fake", "selected_fields": ["signature"]}, "invalid_selection_shape"),
            ({"selected_fields": ["signature", "signature"]}, "duplicate_field"),
            ({"selected_fields": ["invented"]}, "unknown_field"),
            ({"selected_fields": []}, "invalid_selected_fields"),
        ]
        for proposal, reason in bad:
            with self.subTest(reason=reason):
                self.assertEqual(validate_dynamic_selection(ev, proposal, plan)["reason"], reason)


class DynamicGatewayIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "geometry.py").write_text(
            "def analyze_mesh(mesh, matrix, config):\n    return mesh\n", encoding="utf-8")
        (self.root / "caller.py").write_text(
            "from geometry import analyze_mesh\ndef inspect():\n"
            "    return analyze_mesh(1, 2, 3)\n", encoding="utf-8")
        command_init(self.root)
        self.assertEqual(index_project(self.root)["index_state"], "CURRENT")

    def tearDown(self):
        self.tmp.cleanup()

    def test_schema_mode_uses_json_schema_and_keeps_canonical_values(self):
        requests = []

        class MockModel(BaseHTTPRequestHandler):
            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(req)
                data = json.dumps({"choices": [{"message": {
                    "content": json.dumps({"selected_fields": ["path", "line"]})
                }}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format, *args):
                pass

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), MockModel)
        worker = threading.Thread(target=upstream.serve_forever, daemon=True)
        worker.start()
        try:
            gateway = Gateway(
                self.root, upstream=f"http://127.0.0.1:{upstream.server_port}/v1",
                model="qwen-fixture")
            result = gateway.answer({
                "question": "Onde analyze_mesh está definida?",
                "symbol": "analyze_mesh",
                "validation_mode": "dynamic_selection_schema"})
            self.assertEqual(result["status"], "CERTIFIED_FACTS")
            self.assertEqual(result["model_validation"]["status"], "VERIFIED")
            self.assertEqual(result["selected_facts"], {"path": "geometry.py", "line": 1})
            self.assertEqual(requests[0]["response_format"]["type"], "json_schema")
            self.assertNotIn("EXPECTED_OUTPUT", requests[0]["messages"][0]["content"])
            self.assertNotIn("pie:", requests[0]["messages"][0]["content"])
            self.assertNotIn("geometry.py", requests[0]["messages"][0]["content"])
        finally:
            upstream.shutdown()
            upstream.server_close()
            worker.join(timeout=5)

    def test_only_selected_fields_rendered(self):
        def select(question, evidence, *, validation_mode):
            self.assertEqual(validation_mode, "dynamic_selection")
            plan = plan_evidence(question)
            return validate_dynamic_selection(evidence, {
                "selected_fields": ["path", "line"]}, plan)
        result = Gateway(self.root, model_query=select).answer({
            "question": "Onde analyze_mesh está definida?",
            "symbol": "analyze_mesh", "validation_mode": "dynamic_selection"})
        self.assertEqual(result["status"], "CERTIFIED_FACTS")
        self.assertIn("Arquivo: geometry.py", result["answer"])
        self.assertIn("Linha: 1", result["answer"])
        self.assertNotIn("Assinatura:", result["answer"])
        self.assertNotIn("Chamadas diretas verificadas:", result["answer"])

    def test_incorrect_selection_abstains_without_leaking_facts(self):
        def wrong(question, evidence, *, validation_mode):
            return validate_dynamic_selection(evidence, {
                "selected_fields": ["signature"]}, plan_evidence(question))
        result = Gateway(self.root, model_query=wrong).answer({
            "question": "Onde analyze_mesh está definida?",
            "symbol": "analyze_mesh", "validation_mode": "dynamic_selection"})
        self.assertEqual(result["status"], "ABSTAIN")
        self.assertEqual(result["model_validation"]["status"], "REJECTED")
        self.assertNotIn("geometry.py", result["answer"])

    def test_impact_abstains_before_model_call(self):
        def should_not_call(*args, **kwargs):
            self.fail("Unsupported impact query must abstain before model inference")
        result = Gateway(self.root, model_query=should_not_call).answer({
            "question": "Se eu alterar analyze_mesh, o que quebra?",
            "symbol": "analyze_mesh", "validation_mode": "dynamic_selection"})
        self.assertEqual(result["status"], "ABSTAIN")
        self.assertEqual(result["model_validation"]["status"], "NOT_REQUESTED")

    def test_missing_symbol_abstains(self):
        result = Gateway(self.root).answer({
            "question": "Onde nonexistent está definida?",
            "symbol": "nonexistent", "validation_mode": "dynamic_selection"})
        self.assertEqual(result["status"], "ABSTAIN")

    def test_stale_project_abstains(self):
        (self.root / "geometry.py").write_text("def analyze_mesh(revised):\n    return revised\n", encoding="utf-8")
        result = Gateway(self.root).answer({
            "question": "Qual é a assinatura de analyze_mesh?",
            "symbol": "analyze_mesh", "validation_mode": "dynamic_selection"})
        self.assertEqual(result["status"], "ABSTAIN")


if __name__ == "__main__":
    unittest.main()
