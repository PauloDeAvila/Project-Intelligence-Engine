from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pie.certification.controller import (
    ControllerError, audit_record_route, build_manifest, plan_batches,
    validate_manifest,
)
from pie.certification.live_codex import SCHEMA


def scenario(app: str) -> dict:
    if app == "blender":
        return {
            "scenario_id": "blender-material-v1", "prompt": "inspect material",
            "expected_exact": "BLENDER_ORACLE", "model": "gpt-5.6-luna",
            "required_mcp_server": "blender", "description": "fixture",
            "oracle": {"kind": "blender_material_properties", "object_name": "PIE_AB_Cube",
                       "material_name": "PIE_AB_Material", "roughness": 0.35, "metallic": 0.2},
        }
    return {
        "scenario_id": "web-local-v1", "prompt": "inspect local page",
        "expected_exact": "WEB_ORACLE", "model": "gpt-5.6-luna",
        "required_mcp_server": "web", "description": "fixture",
        "oracle": {"kind": "web_local_page", "fixture_id": "phase3-local",
                   "required_refs": ["e1", "e2"], "required_text": ["Products"]},
    }


class ControllerTests(unittest.TestCase):
    def test_manifest_and_batches_are_fixed_and_plan_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_manifest(scenarios=[scenario("blender"), scenario("web")],
                                      workspace=Path(tmp), baseline_profile="baseline",
                                      optimized_profile="optimized")
        self.assertEqual(validate_manifest(manifest)["sessions"], 12)
        batches = plan_batches(manifest)
        self.assertEqual(batches["pilot"]["sessions"], 4)
        self.assertEqual(batches["complement"]["sessions"], 8)
        self.assertFalse(batches["automatic_execution"])
        self.assertEqual(manifest["execution"], "PLAN_ONLY_NO_MODEL_EXECUTION")

    def test_manifest_rejects_duplicate_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_manifest(scenarios=[scenario("blender"), scenario("web")],
                                      workspace=Path(tmp), baseline_profile="baseline",
                                      optimized_profile="optimized")
        manifest["scenarios"][1]["run_id"] = manifest["scenarios"][0]["run_id"]
        with self.assertRaises(ControllerError):
            validate_manifest(manifest)

    def test_route_audit_requires_exact_ids_not_timestamps(self):
        record = {
            "schema": SCHEMA, "provider_reported": True, "source": "codex_exec_json_turn_completed",
            "condition": "optimized", "scenario_id": "web-local-v1", "repetition": 1,
            "run_id": "optimized-run", "pair_id": "pair-web", "model": "m", "codex_version": "c",
            "prompt_sha256": "p", "expected_sha256": "e", "workspace_commit": "w",
            "configuration_sha256": "cfg", "oracle_kind": "exact_text", "oracle_pass": True,
            "tool_events": 1, "expected_mcp_server": "pie-web-optimized", "mcp_route_verified": True,
            "mcp_tools": [{"server": "pie-web-optimized", "tool": "browser_snapshot", "status": "completed"}],
            "runtime_ms": 1.0, "usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 1},
        }
        result = audit_record_route(record, [{"event": "MCP_TOOL_CALL_RECEIVED", "run_id": "other",
                                              "pair_id": "pair-web", "gateway_server": "pie-web-optimized"}])
        self.assertEqual(result["decision"], "INSUFFICIENT_EVIDENCE")

    def test_route_audit_accepts_exact_correlation(self):
        record = {
            "schema": SCHEMA, "provider_reported": True, "source": "codex_exec_json_turn_completed",
            "condition": "optimized", "scenario_id": "web-local-v1", "repetition": 1,
            "run_id": "optimized-run", "pair_id": "pair-web", "model": "m", "codex_version": "c",
            "prompt_sha256": "p", "expected_sha256": "e", "workspace_commit": "w",
            "configuration_sha256": "cfg", "oracle_kind": "exact_text", "oracle_pass": True,
            "tool_events": 1, "expected_mcp_server": "pie-web-optimized", "mcp_route_verified": True,
            "mcp_tools": [{"server": "pie-web-optimized", "tool": "browser_snapshot", "status": "completed"}],
            "runtime_ms": 1.0, "usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 1},
        }
        result = audit_record_route(record, [{"event": "MCP_TOOL_CALL_RECEIVED", "run_id": "optimized-run",
                                              "pair_id": "pair-web", "gateway_server": "pie-web-optimized"}])
        self.assertEqual(result["decision"], "VALID")

