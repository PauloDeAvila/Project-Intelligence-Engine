from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pie.certification.controller import (
    ControllerError, audit_record_route, build_manifest, plan_batches,
    load_scenario, run_pilot, run_single, validate_batch_budget, validate_manifest,
)
from pie.certification.live_codex import CodexCaptureError, SCHEMA


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
    def test_selective_blender_scenario_uses_controller_contract(self):
        path = Path(__file__).resolve().parents[1] / "benchmarks" / "phase3" / "blender-selective-task-a-scenario.json"
        loaded = load_scenario(path)
        self.assertEqual(loaded["scenario_id"], "blender-selective-location-v1")
        self.assertEqual(loaded["expected_mcp_tools_by_condition"]["baseline"], ["get_scene_info"])
        self.assertEqual(loaded["expected_mcp_tools_by_condition"]["optimized"], ["pie_blender_query_scene"])

    def test_single_run_preserves_plan_identity_before_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("pie.certification.controller.preflight_codex",
                       return_value={"state": "BLOCKED", "errors": ["offline-test"]}):
                result = run_single(
                    scenario=scenario("blender"), application="blender", condition="baseline",
                    workspace=root, baseline_home=root / "baseline", optimized_home=root / "optimized",
                    baseline_profile="baseline", optimized_profile="optimized", output=root / "result.json",
                    pair_id_override="pair-plan-fixed", run_id_override="baseline-plan-fixed")
            self.assertEqual(result["run_id"], "baseline-plan-fixed")
            self.assertEqual(result["pair_id"], "pair-plan-fixed")
            self.assertFalse(result["quota_consumed"])

    def test_pilot_persists_sanitized_usage_on_route_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            manifest=build_manifest(scenarios=[scenario("blender"), scenario("web")],
                                    workspace=root, baseline_profile="baseline",
                                    optimized_profile="optimized")
            failure=CodexCaptureError("MCP route evidence failed", evidence={
                "usage":{"input_tokens":12,"cached_input_tokens":4,"output_tokens":2},
                "mcp_tools":[{"server":"blender","tool":"execute_blender_code","status":"failed"}],
                "provider_reported":True})
            with patch("pie.certification.controller.preflight_codex",
                       return_value={"state":"READY_FOR_BENCHMARK"}), \
                 patch("pie.certification.controller.capture_codex", side_effect=failure):
                result=run_pilot(manifest=manifest, scenarios=[scenario("blender"), scenario("web")],
                                 workspace=root, baseline_home=root/"baseline", optimized_home=root/"optimized",
                                 baseline_profile="baseline", optimized_profile="optimized",
                                 output=root/"pilot.json", authorized_sessions=4)
            self.assertEqual(result["state"], "AB_PILOT_FAILED")
            self.assertEqual(result["authorization"]["consumed_sessions"], 1)
            evidence=result["failed_execution"]["provider_evidence"]
            self.assertEqual(evidence["usage"]["input_tokens"], 12)
            self.assertEqual(evidence["mcp_tools"][0]["status"], "failed")

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
        self.assertEqual(validate_batch_budget(manifest, "pilot", 4)["sessions"], 4)
        with self.assertRaises(ControllerError):
            validate_batch_budget(manifest, "pilot", 12)

    def test_manifest_rejects_duplicate_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_manifest(scenarios=[scenario("blender"), scenario("web")],
                                      workspace=Path(tmp), baseline_profile="baseline",
                                      optimized_profile="optimized")
        manifest["scenarios"][1]["run_id"] = manifest["scenarios"][0]["run_id"]
        with self.assertRaises(ControllerError):
            validate_manifest(manifest)

    def test_pilot_rejects_manifest_for_different_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            manifest=build_manifest(scenarios=[scenario("blender"), scenario("web")],
                                    workspace=root, baseline_profile="baseline",
                                    optimized_profile="optimized")
            changed=scenario("blender")
            changed["prompt"]="different prompt"
            with self.assertRaises(ControllerError) as error:
                run_pilot(manifest=manifest, scenarios=[changed, scenario("web")],
                          workspace=root, baseline_home=root/"baseline", optimized_home=root/"optimized",
                          baseline_profile="baseline", optimized_profile="optimized",
                          output=root/"pilot.json", authorized_sessions=4)
            self.assertIn("Manifest identity", str(error.exception))

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

