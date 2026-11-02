import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from semantic_gate import verify_fields

class SemanticGateTests(unittest.TestCase):
    def test_correct_contract_is_approved(self):
        expected={"count":1,"verified":True,"error":"AttributeError"}
        self.assertTrue(verify_fields(json.dumps(expected),expected)["approved"])
    def test_wrong_boolean_type_is_rejected(self):
        self.assertFalse(verify_fields('{"verified":1}',{"verified":True})["approved"])
    def test_missing_fields_are_rejected(self):
        self.assertFalse(verify_fields('{}',{"verified":True})["approved"])
    def test_fabricated_fields_are_rejected(self):
        self.assertFalse(verify_fields('{"verified":true,"invented":3}',{"verified":True})["approved"])
    def test_non_json_is_rejected(self):
        self.assertFalse(verify_fields("nonsense",{"verified":True})["approved"])

if __name__=="__main__":
    unittest.main()
