"""Regression tests for independent real-project Context Pack v2 verification."""
from __future__ import annotations

import copy
from hashlib import sha256
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "validate_static_context_projects.py"
SPEC = importlib.util.spec_from_file_location("pie_real_project_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RealProjectValidationContractTests(unittest.TestCase):
    def setUp(self):
        source = b"def action():\n    pass\n"
        consumer = b"from mod import action\naction()\n"
        self.snapshot = {"mod.py": source, "consumer.py": consumer}
        binding = "definition:mod.action"
        self.pack = {
            "schema_version": "pie-context-pack-v2",
            "status": "VERIFIED_STATIC_CONTEXT",
            "definition": {
                "path": "mod.py", "line": 1,
                "sha256": sha256(source).hexdigest(),
                "binding": binding,
            },
            "callers": [{
                "path": "consumer.py", "line": 2,
                "source_sha256": sha256(consumer).hexdigest(),
                "target_binding": binding,
                "resolution": "verified",
                "usage_kind": "direct_call",
            }],
            "coverage": {
                "static_analysis_coverage": "PARTIAL",
                "exhaustive": False,
                "returned_verified_call_list_complete": True,
                "omitted_by_budget": 0,
                "omitted_by_call_limit": 0,
                "returned_direct_call_count": 1,
                "verified_direct_call_count": 1,
            },
            "impact": {
                "status": "UNDETERMINED",
                "breaking_change_proven": False,
            },
        }

    def test_accepts_consistent_v2_provenance(self):
        MODULE.verify_pack_source_contract(self.pack, self.snapshot)

    def test_rejects_tampered_definition_hash(self):
        pack = copy.deepcopy(self.pack)
        pack["definition"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(AssertionError, "hash mismatch"):
            MODULE.verify_pack_source_contract(pack, self.snapshot)

    def test_rejects_tampered_caller_hash(self):
        pack = copy.deepcopy(self.pack)
        pack["callers"][0]["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(AssertionError, "hash mismatch"):
            MODULE.verify_pack_source_contract(pack, self.snapshot)

    def test_rejects_paths_outside_snapshot(self):
        pack = copy.deepcopy(self.pack)
        pack["definition"]["path"] = "../elsewhere.py"
        with self.assertRaisesRegex(AssertionError, "Unrecognized source path"):
            MODULE.verify_pack_source_contract(pack, self.snapshot)

    def test_rejects_false_completeness_and_impact_claims(self):
        for field, value in [
            ("exhaustive", True),
            ("static_analysis_coverage", "COMPLETE"),
            ("returned_verified_call_list_complete", False),
            ("omitted_by_budget", 1),
            ("verified_direct_call_count", 2),
        ]:
            with self.subTest(field=field):
                pack = copy.deepcopy(self.pack)
                pack["coverage"][field] = value
                with self.assertRaises(AssertionError):
                    MODULE.verify_pack_source_contract(pack, self.snapshot)
        pack = copy.deepcopy(self.pack)
        pack["impact"]["breaking_change_proven"] = True
        with self.assertRaisesRegex(AssertionError, "runtime-impact"):
            MODULE.verify_pack_source_contract(pack, self.snapshot)

    def test_rejects_unsupported_call_and_invalid_lines(self):
        for field, value in [
            ("resolution", "inferred"),
            ("usage_kind", "attribute_read"),
            ("target_binding", "other"),
            ("line", 3),
        ]:
            with self.subTest(field=field):
                pack = copy.deepcopy(self.pack)
                pack["callers"][0][field] = value
                with self.assertRaises(AssertionError):
                    MODULE.verify_pack_source_contract(pack, self.snapshot)

    def test_rejects_wrong_schema(self):
        pack = copy.deepcopy(self.pack)
        pack["schema_version"] = "pie-context-pack-v1"
        with self.assertRaisesRegex(AssertionError, "schema version"):
            MODULE.verify_pack_source_contract(pack, self.snapshot)


if __name__ == "__main__":
    unittest.main()
