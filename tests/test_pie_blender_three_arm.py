"""Three-arm gate tests use synthetic records; they prove arithmetic, not model savings."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from certify_pie_blender_three_arm import assess


def entry(condition, tokens=1000, *, correct=True, scene="scene-sha-1", repetition=1):
    return {
        "scenario_id": "material-roughness",
        "repetition": repetition,
        "model": "test-model",
        "blender_version": "4.5.0",
        "scene_sha256": scene,
        "task_sha256": "fixed-task-hash",
        "sampling_sha256": "fixed-model-settings-hash",
        "oracle_id": "fixture-oracle-1",
        "condition": condition,
        "prompt_tokens": tokens,
        "completion_tokens": 50,
        "wall_ms": 100.5,
        "correct": correct,
    }


class ThreeArmGateTests(unittest.TestCase):
    def test_complete_hypothetical_pairs_pass_measurement_gate_only(self):
        rows = [entry("baseline", 1000), entry("pie_current", 500),
                entry("pie_optimized", 100)]
        v = assess({"records": rows}, min_pairs=1)
        self.assertEqual(v["status"], "MEASUREMENT_GATE_PASSED")
        self.assertEqual(v["paired_input_token_savings_pct"], 90.0)
        self.assertTrue(v["external_evidence_review_required"])
        self.assertEqual(v["complete_paired_trials"], 1)

    def test_missing_token_counts_are_never_zero_filled(self):
        rows = [entry("baseline"), entry("pie_current"), entry("pie_optimized")]
        rows[2]["prompt_tokens"] = None
        v = assess({"records": rows}, min_pairs=1)
        self.assertEqual(v["status"], "NOT_CERTIFIED")
        self.assertEqual(v["invalid_records"], [2])
        self.assertIsNone(v["paired_input_token_savings_pct"])

    def test_different_scene_never_paired(self):
        rows = [entry("baseline"), entry("pie_current"),
                entry("pie_optimized", scene="different-sha")]
        v = assess({"records": rows}, min_pairs=1)
        self.assertEqual(v["complete_paired_trials"], 0)
        self.assertGreater(v["incomplete_groups"], 0)

    def test_task_or_sampling_drift_never_paired(self):
        rows = [entry("baseline"), entry("pie_current"), entry("pie_optimized")]
        rows[2]["task_sha256"] = "another-task"
        self.assertEqual(assess({"records": rows}, min_pairs=1)["complete_paired_trials"], 0)
        rows[2]["task_sha256"] = "fixed-task-hash"
        rows[2]["sampling_sha256"] = "different-model-settings"
        self.assertEqual(assess({"records": rows}, min_pairs=1)["complete_paired_trials"], 0)

    def test_correctness_regression_blocks_claim(self):
        rows = [entry("baseline", 1000, correct=True),
                entry("pie_current", 500, correct=True),
                entry("pie_optimized", 50, correct=False)]
        v = assess({"records": rows}, min_pairs=1)
        self.assertEqual(v["status"], "NOT_CERTIFIED")
        self.assertFalse(v["optimized_no_correctness_regression"])

    def test_duplicate_record_and_insufficient_pairs_block_claim(self):
        rows = [entry("baseline"), entry("pie_current"), entry("pie_optimized", 100)]
        self.assertEqual(assess({"records": rows}, min_pairs=10)["status"], "NOT_CERTIFIED")
        v = assess({"records": [*rows, rows[0]]}, min_pairs=1)
        self.assertEqual(v["status"], "NOT_CERTIFIED")
        self.assertEqual(len(v["duplicate_records"]), 1)

    def test_cli_emits_explicit_not_certified_without_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "trials.json"
            path.write_text('{"records":[]}', encoding="utf8")
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parents[1] /
                                     "tools" / "certify_pie_blender_three_arm.py"),
                 "--input", str(path), "--strict"],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(json.loads(proc.stdout)["status"], "NOT_CERTIFIED")


if __name__ == "__main__":
    unittest.main()
