"""DES-04 immutable evaluation manifest gate.

No repository or model is executed by this tool. It verifies that a proposed
real-repository evaluation has been independently reviewed and fully pinned
BEFORE any scored experiment begins.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

COMMIT = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_CATEGORIES = {
    "unambiguous_static_direct_call", "ambiguous_symbol_name",
    "multi_file_evidence", "dynamic_or_indirect_call_limit",
    "stale_source_changed", "stale_new_file",
    "unresolved_reference", "not_enough_evidence_for_breakage",
}
SAFE_LABELS = {"VERIFIED_STATIC", "POSSIBLE_UNVERIFIED", "ABSTAIN"}


def validate_manifest(document: dict) -> dict:
    if not isinstance(document, dict) or document.get("schema_version") != "des04-eval-v1":
        raise ValueError("Unsupported evaluation schema")
    if document.get("status") != "FROZEN":
        raise ValueError("Evaluation is not frozen: model scoring forbidden")
    repos = document.get("repositories")
    if not isinstance(repos, list) or len(repos) < 2:
        raise ValueError("At least two real, pinned repositories required")
    names = set()
    for repository in repos:
        if not isinstance(repository, dict):
            raise ValueError("Invalid repository entry")
        name = repository.get("name")
        commit = repository.get("commit_sha")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Repository name invalid or duplicate")
        names.add(name)
        if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
            raise ValueError(f"Repository {name} is not pinned to a full SHA")
        if repository.get("clean_checkout") is not True:
            raise ValueError(f"Repository {name} has not passed clean-tree verification")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) < len(repos) * 8:
        raise ValueError("Need at least eight independently labeled cases per repo")
    ids = set()
    categories = set()
    counts = {name: 0 for name in names}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Invalid case")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in ids:
            raise ValueError("Duplicate or invalid case_id")
        ids.add(case_id)
        name = case.get("repository")
        if name not in names:
            raise ValueError("Case has unknown repository")
        counts[name] += 1
        question = case.get("question")
        if not isinstance(question, str) or len(question.strip()) < 8:
            raise ValueError("Missing meaningful question")
        category = case.get("category")
        if category not in REQUIRED_CATEGORIES:
            raise ValueError("Unsupported case category")
        categories.add(category)
        if case.get("expected_status") not in SAFE_LABELS:
            raise ValueError("Case missing a valid expected status")
        if case.get("expected_breakage") is not False:
            raise ValueError("Unproven breakage claim in static traceability gold")
        citations = case.get("source_spans")
        if not isinstance(citations, list):
            raise ValueError("Case needs reviewed source-spans list")
        if case["expected_status"] == "VERIFIED_STATIC" and not citations:
            raise ValueError("Verified static case must have reviewed source locations")
        for span in citations:
            if not isinstance(span, dict) or not isinstance(span.get("path"), str):
                raise ValueError("Source span lacks path")
            if type(span.get("line")) is not int or span["line"] < 1:
                raise ValueError("Source span needs positive line number")
        reviewers = case.get("reviewers")
        if not isinstance(reviewers, list) or len(set(reviewers)) < 2 or any(
            not isinstance(r, str) or not r.strip() for r in reviewers
        ):
            raise ValueError("Two distinct reviewers required for each gold case")
        if case.get("gold_frozen_before_inference") is not True:
            raise ValueError("Case gold was not frozen before inference")
    if categories != REQUIRED_CATEGORIES:
        raise ValueError("Case categories incomplete")
    if any(count < 8 for count in counts.values()):
        raise ValueError("Each repository needs eight reviewed cases")
    return {
        "status": "READY_FOR_SCORE",
        "repositories": len(repos),
        "cases": len(cases),
        "category_count": len(categories),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate frozen DES-04 gold before inference")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    raw = args.manifest.read_bytes()
    content = json.loads(raw)
    result = validate_manifest(content)
    result["manifest_sha256"] = sha256(raw).hexdigest()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
