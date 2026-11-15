"""Forensic regressions for fail-closed Codex/MCP capture.

These tests never start Codex.  They exercise the parser, the capture boundary,
and the controller with deterministic subprocess doubles so a failure cannot
silently become a retry or a certifying record.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pie.certification import controller
from pie.certification.live_codex import (
    CodexCaptureError,
    capture_codex,
    parse_codex_jsonl,
)


def _trace(*, tool_status: str = "completed", usage: dict | None = None,
           answer: str = "answer", suffix: str = "") -> str:
    usage = usage or {
        "input_tokens": 10,
        "cached_input_tokens": 2,
        "output_tokens": 3,
        "reasoning_output_tokens": 0,
    }
    events = [
        {"type": "thread.started", "thread_id": "opaque"},
        {"type": "item.started", "item": {"type": "mcp_tool_call"}},
        {"type": "item.completed", "item": {
            "type": "mcp_tool_call", "server": "blender",
            "tool": "get_scene_info", "status": tool_status,
        }},
        {"type": "item.completed", "item": {
            "type": "agent_message", "text": answer,
        }},
        {"type": "turn.completed", "usage": usage},
    ]
    return "\n".join(json.dumps(event) for event in events) + "\n" + suffix


def _scenario() -> dict:
    return {
        "scenario_id": "blender-forensic-v1",
        "prompt": "Inspect the disposable Blender fixture.",
        "expected_exact": "answer",
        "model": "gpt-5.6-luna",
        "description": "forensic regression",
        "required_mcp_server": "blender",
        "oracle": {"kind": "blender_material_properties",
                    "object_name": "PIE_AB_Cube", "material_name": "PIE_AB_Material",
                    "roughness": 0.35, "metallic": 0.2},
    }


def _completed(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["codex"], 0, stdout, "")


class CaptureBoundaryTests(unittest.TestCase):
    def _capture(self, exec_result, *, scenario=None):
        scenario = scenario or _scenario()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("pie.certification.live_codex._git_clean_commit", return_value="0" * 40), \
                 patch("pie.certification.live_codex._codex_environment", return_value=({}, "config")), \
                 patch("pie.certification.live_codex.preflight_codex",
                       return_value={"state": "READY_FOR_BENCHMARK"}), \
                 patch("pie.certification.live_codex.shutil.which", return_value="codex"), \
                 patch("pie.certification.live_codex.subprocess.run",
                       side_effect=[_completed("codex 1.0\n"), exec_result]) as run:
                outcome = None
                error = None
                try:
                    outcome = capture_codex(
                        scenario, condition="baseline", repetition=1,
                        workspace=root, codex_home=root, profile="baseline",
                    )
                except Exception as exc:  # assertions below classify the boundary
                    error = exc
                return outcome, error, run

    def test_mcp_tool_error_preserves_sanitized_usage_and_does_not_retry(self):
        _, error, run = self._capture(_completed(_trace(tool_status="failed")))
        self.assertIsInstance(error, CodexCaptureError)
        self.assertIn("MCP route evidence failed", str(error))
        self.assertEqual(error.evidence["usage"]["input_tokens"], 10)
        self.assertEqual(error.evidence["mcp_tools"][0]["status"], "failed")
        self.assertEqual(run.call_count, 2)  # version + exactly one exec

    def test_exit_code_one_is_non_certifying_and_does_not_retry(self):
        _, error, run = self._capture(
            subprocess.CompletedProcess(["codex"], 1, "", "sanitized failure")
        )
        self.assertIsInstance(error, CodexCaptureError)
        self.assertIn("exit code 1", str(error))
        self.assertEqual(run.call_count, 2)

    def test_truncated_jsonl_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Malformed Codex JSONL"):
            parse_codex_jsonl(_trace() + '{"type":"turn.completed"')

    def test_missing_usage_is_rejected_and_never_becomes_zero(self):
        trace = _trace().replace(
            '"usage": {"input_tokens": 10, "cached_input_tokens": 2, '
            '"output_tokens": 3, "reasoning_output_tokens": 0}',
            '"usage": null',
        )
        with self.assertRaisesRegex(ValueError, "Missing provider usage"):
            parse_codex_jsonl(trace)

    def test_approval_failure_is_rejected_without_retry(self):
        trace = json.dumps({"type": "error", "message": "approval required"}) + "\n"
        _, error, run = self._capture(_completed(trace))
        self.assertIsInstance(error, CodexCaptureError)
        self.assertIn("JSONL/provider usage evidence unavailable", str(error))
        self.assertTrue(Path(error.evidence["forensic_path"]).is_dir())
        self.assertEqual(run.call_count, 2)

    def test_timeout_is_terminal_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeout = subprocess.TimeoutExpired(["codex"], 1)
            with patch("pie.certification.live_codex._git_clean_commit", return_value="0" * 40), \
                 patch("pie.certification.live_codex._codex_environment", return_value=({}, "config")), \
                 patch("pie.certification.live_codex.preflight_codex",
                       return_value={"state": "READY_FOR_BENCHMARK"}), \
                 patch("pie.certification.live_codex.shutil.which", return_value="codex"), \
                 patch("pie.certification.live_codex.subprocess.run",
                       side_effect=[_completed("codex 1.0\n"), timeout]) as run:
                with self.assertRaisesRegex(RuntimeError, "unavailable/timeout"):
                    capture_codex(_scenario(), condition="baseline", repetition=1,
                                  workspace=root, codex_home=root,
                                  profile="baseline")
                self.assertEqual(run.call_count, 2)

    def test_premature_exit_without_turn_completed_is_rejected(self):
        trace = json.dumps({"type": "thread.started", "thread_id": "opaque"}) + "\n"
        _, error, run = self._capture(_completed(trace))
        self.assertIsInstance(error, CodexCaptureError)
        self.assertIn("JSONL/provider usage evidence unavailable", str(error))
        self.assertTrue(Path(error.evidence["forensic_path"]).is_dir())
        self.assertEqual(run.call_count, 2)

    def test_expected_tool_allowlist_is_exact_and_ordered(self):
        scenario = _scenario()
        scenario["expected_mcp_tools"] = ["get_scene_info"]
        outcome, error, _ = self._capture(_completed(_trace()), scenario=scenario)
        self.assertIsNone(error)
        self.assertTrue(outcome["mcp_route_verified"])
        scenario["expected_mcp_tools"] = ["execute_blender_code"]
        _, error, _ = self._capture(_completed(_trace()), scenario=scenario)
        self.assertIsInstance(error, CodexCaptureError)
        self.assertIn("tool allowlist failed", str(error))


class ControllerBoundaryTests(unittest.TestCase):
    def test_single_run_persists_budget_before_capture(self):
        scenario = _scenario()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "single.json"
            observed = {}

            def fake_capture(*args, **kwargs):
                ledger = output.parent / "single-budget-ledger.json"
                observed.update(json.loads(ledger.read_text(encoding="utf-8")))
                return {"run_id": kwargs["run_id_override"],
                        "pair_id": kwargs["pair_id_override"]}

            with patch("pie.certification.controller.preflight_codex",
                       return_value={"state": "READY_FOR_BENCHMARK"}), \
                 patch("pie.certification.controller.capture_codex", side_effect=fake_capture), \
                 patch("pie.certification.controller._fixture_oracle",
                       return_value={"passed": True, "kind": "blender_material_properties"}), \
                 patch("pie.certification.controller.audit_record_route",
                       return_value={"decision": "VALID", "reason": "test"}), \
                 patch("pie.certification.controller.import_provider_record"):
                result = controller.run_single(
                    scenario=scenario, application="blender", condition="baseline",
                    workspace=root, baseline_home=root, optimized_home=root,
                    baseline_profile="baseline", optimized_profile="optimized",
                    output=output)
            self.assertEqual(result["state"], "BASELINE_BLENDER_VALID")
            self.assertTrue(result["pair_id"].startswith("pair-"))
            self.assertEqual(observed["state"], "started")
            self.assertEqual(observed["consumed_sessions"], 1)
            self.assertEqual(observed["remaining_sessions"], 0)
            self.assertFalse(observed["automatic_retry"])

    def test_single_run_accepts_pair_id_for_paired_arm(self):
        scenario = _scenario()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "single.json"
            with patch("pie.certification.controller.preflight_codex",
                       return_value={"state": "READY_FOR_BENCHMARK"}), \
                 patch("pie.certification.controller.capture_codex",
                       side_effect=lambda *args, **kwargs: {
                           "run_id": kwargs["run_id_override"],
                           "pair_id": kwargs["pair_id_override"]}), \
                 patch("pie.certification.controller._fixture_oracle",
                       return_value={"passed": True, "kind": "blender_material_properties"}), \
                 patch("pie.certification.controller.audit_record_route",
                       return_value={"decision": "VALID", "reason": "test"}), \
                 patch("pie.certification.controller.import_provider_record"):
                result = controller.run_single(
                    scenario=scenario, application="blender", condition="optimized",
                    workspace=root, baseline_home=root, optimized_home=root,
                    baseline_profile="baseline", optimized_profile="optimized",
                    output=output, pair_id_override="pair-fixed")
            self.assertEqual(result["state"], "OPTIMIZED_BLENDER_VALID")
            self.assertEqual(result["pair_id"], "pair-fixed")

    def test_persistence_failure_returns_blocked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scenario_paths = []
            for name, app in (("blender", "blender"), ("web", "web")):
                path = root / f"{name}.json"
                scenario = _scenario()
                scenario["scenario_id"] = name
                scenario["required_mcp_server"] = app
                scenario["oracle"] = {"kind": "web_local_page", "fixture_id": "x",
                                       "required_refs": [], "required_text": []} if app == "web" else scenario["oracle"]
                path.write_text(json.dumps(scenario), encoding="utf-8")
                scenario_paths.append(path)
            with patch("pie.certification.controller._write_json", side_effect=OSError("disk full")) as write:
                code = controller.main([
                    "plan", "--workspace", str(root),
                    "--baseline-profile", "baseline",
                    "--optimized-profile", "optimized",
                    "--scenario", str(scenario_paths[0]),
                    "--scenario", str(scenario_paths[1]),
                    "--output", str(root / "plan.json"),
                ])
            self.assertEqual(code, 2)
            self.assertEqual(write.call_count, 1)

    def test_invalid_oracle_is_rejected_before_capture(self):
        scenario = _scenario()
        scenario["oracle"] = {"kind": "accept_anything"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            path.write_text(json.dumps(scenario), encoding="utf-8")
            with self.assertRaises(controller.ControllerError):
                controller.load_scenario(path)

    def test_controller_stops_after_first_capture_failure(self):
        scenario = _scenario()
        entries = []
        for condition in ("baseline", "optimized"):
            entries.append({
                "application": "blender", "scenario_id": scenario["scenario_id"],
                "pair_id": "pair-one", "run_id": f"{condition}-one",
                "repetition": 1, "condition": condition, "model": scenario["model"],
                "prompt_sha256": controller._sha(scenario["prompt"]),
                "expected_sha256": controller._sha(scenario["expected_exact"]),
                "workspace_root": "", "profile": condition,
                "expected_mcp_server": "blender" if condition == "baseline" else "pie-blender-optimized",
                "oracle": scenario["oracle"],
            })
        entries.extend([dict(entries[0], run_id="baseline-two", repetition=1),
                        dict(entries[1], run_id="optimized-two", repetition=1)])
        manifest = {"schema": controller.SCHEMA, "state": "READY_FOR_AB_PILOT",
                    "scenarios": entries, "workspace_root": ""}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest["workspace_root"] = str(root)
            failure = CodexCaptureError("tool failed", evidence={"status": "failed"})
            with patch("pie.certification.controller.validate_manifest"), \
                 patch("pie.certification.controller.validate_batch_budget"), \
                 patch("pie.certification.controller.preflight_codex",
                       return_value={"state": "READY_FOR_BENCHMARK"}), \
                 patch("pie.certification.controller.capture_codex", side_effect=failure) as capture:
                result = controller.run_pilot(
                    manifest=manifest, scenarios=[scenario], workspace=root,
                    baseline_home=root, optimized_home=root,
                    baseline_profile="baseline", optimized_profile="optimized",
                    output=root / "result.json", authorized_sessions=4,
                )
            self.assertEqual(result["state"], "AB_PILOT_FAILED")
            self.assertEqual(result["authorization"]["consumed_sessions"], 1)
            self.assertFalse(result["authorization"]["automatic_retry"])
            self.assertEqual(capture.call_count, 1)


if __name__ == "__main__":
    unittest.main()
