import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "tools" / "codex_paired_benchmark.py"
SPEC = importlib.util.spec_from_file_location("codex_paired_benchmark", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_structured_score_normalizes_absolute_paths_and_nested_calls():
    gold = {
        "definitions": {"audit_component": ["ai_mesh_doctor/quality.py", 158]},
        "callers": {
            "audit_component": [
                ["ai_mesh_doctor/batch.py", 62],
                ["ai_mesh_doctor/capture.py", 115],
            ]
        },
    }
    answer = json.dumps(
        {
            "definition": {
                "path": r"C:\workspace\Doctor Mesh\ai_mesh_doctor\quality.py",
                "line": 158,
            },
            "callers": [
                {
                    "path": r"C:\workspace\Doctor Mesh\ai_mesh_doctor\batch.py",
                    "line": 62,
                },
                {
                    "path": r"C:\workspace\Doctor Mesh\ai_mesh_doctor\capture.py",
                    "calls": [{"line": 115}],
                },
            ],
        }
    )
    result = MODULE.structured_score(answer, gold, "audit_component", Path(r"C:\workspace\Doctor Mesh"))
    assert result == {
        "passed": True,
        "definition_match": True,
        "callers_match": True,
        "actual_call_count": 2,
        "expected_call_count": 2,
    }


def test_structured_score_rejects_missing_caller():
    gold = {"definitions": {"audit_component": ["ai_mesh_doctor/quality.py", 158]}, "callers": {"audit_component": [["ai_mesh_doctor/capture.py", 115]]}}
    answer = json.dumps({"definition": {"path": "ai_mesh_doctor/quality.py", "line": 158}, "callers": []})
    result = MODULE.structured_score(answer, gold, "audit_component", Path("Doctor Mesh"))
    assert result["definition_match"] is True
    assert result["callers_match"] is False
    assert result["passed"] is False
