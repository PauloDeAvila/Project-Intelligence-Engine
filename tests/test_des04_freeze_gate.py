"""DES-04 frozen-manifest policy is fail-closed and independent of Qwen."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "des04_freeze", ROOT / "tools" / "des04_validate_freeze.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

CATEGORIES = (
    "unambiguous_static_direct_call", "ambiguous_symbol_name",
    "multi_file_evidence", "dynamic_or_indirect_call_limit",
    "stale_source_changed", "stale_new_file",
    "unresolved_reference", "not_enough_evidence_for_breakage",
)


def fixture() -> dict:
    cases = []
    for name in ("alpha", "beta"):
        for i, category in enumerate(CATEGORIES, 1):
            status = "VERIFIED_STATIC" if category in (
                "unambiguous_static_direct_call", "multi_file_evidence"
            ) else "ABSTAIN"
            cases.append({
                "case_id": f"{name}-{i}",
                "repository": name,
                "question": f"Audit {category} for a source reference",
                "category": category,
                "expected_status": status,
                "expected_breakage": False,
                "source_spans": [{"path": "module.py", "line": 1}] if status == "VERIFIED_STATIC" else [],
                "reviewers": ["reviewer-one", "reviewer-two"],
                "gold_frozen_before_inference": True,
            })
    return {
        "schema_version": "des04-eval-v1",
        "status": "FROZEN",
        "repositories": [
            {"name": name, "commit_sha": "a" * 40, "clean_checkout": True}
            for name in ("alpha", "beta")
        ],
        "cases": cases,
    }


class FreezeGateTests(unittest.TestCase):
    def test_complete_reviewed_fixture(self):
        self.assertEqual(module.validate_manifest(fixture())["cases"], 16)

    def test_draft_cannot_be_scored(self):
        doc = fixture()
        doc["status"] = "DRAFT_NOT_FROZEN"
        with self.assertRaisesRegex(ValueError, "not frozen"):
            module.validate_manifest(doc)

    def test_short_commit_sha_refused(self):
        doc = fixture()
        doc["repositories"][0]["commit_sha"] = "abc123"
        with self.assertRaisesRegex(ValueError, "full SHA"):
            module.validate_manifest(doc)

    def test_single_reviewer_refused(self):
        doc = fixture()
        doc["cases"][0]["reviewers"] = ["reviewer-one"]
        with self.assertRaisesRegex(ValueError, "Two distinct reviewers"):
            module.validate_manifest(doc)

    def test_unverified_breakage_cannot_enter_gold(self):
        doc = fixture()
        doc["cases"][0]["expected_breakage"] = True
        with self.assertRaisesRegex(ValueError, "Unproven breakage"):
            module.validate_manifest(doc)

    def test_static_verification_requires_path_and_line(self):
        doc = fixture()
        doc["cases"][0]["source_spans"] = []
        with self.assertRaisesRegex(ValueError, "source locations"):
            module.validate_manifest(doc)

    def test_dirty_repo_cannot_be_frozen(self):
        doc = fixture()
        doc["repositories"][0]["clean_checkout"] = False
        with self.assertRaisesRegex(ValueError, "clean-tree"):
            module.validate_manifest(doc)


if __name__ == "__main__":
    unittest.main()
