"""Offline, deterministic checks for paired OpenCode v2 benchmarking."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from benchmark_opencode_pair import _parse_final, load_questions, summarize, run


def messages(with_pie: bool, answer: str) -> list[dict]:
    tool = [{"type": "tool", "name": "pie_pie_project_status",
             "id": "tool1", "state": {"status": "completed",
             "content": [{"type": "text", "text": "CURRENT"}]}}] if with_pie else []
    return [
        {"type": "user", "id": "user"},
        {"type": "assistant", "finish": "tool-calls", "content": tool},
        {"type": "assistant", "finish": "stop", "id": "final",
         "tokens": {"input": 20 if with_pie else 100, "output": 5},
         "content": [{"type": "text", "text": "ANSWER: " + answer}]},
        {"type": "idle", "outcome": "succeeded"}
    ]


class Fake:
    def __init__(self, root: Path, pie: bool, answer: str = "command_status"):
        self.root, self.pie, self.answer = root, pie, answer
        self.sessions: list[str] = []

    def _location_matches(self, response, root):
        return response["location"]["directory"] == str(root)

    def _data(self, response):
        return response["data"]

    def _request(self, method, path, body=None):
        if path == "/mcp":
            return {"location": {"directory": str(self.root)},
                    "data": ([{"name": "pie",
                               "status": {"status": "connected"}}]
                             if self.pie else [])}
        if method == "POST" and path == "/session":
            session = "ses_" + str(len(self.sessions) + 1)
            self.sessions.append(session)
            return {"data": {"id": session,
                             "location": {"directory": str(self.root)}}}
        if path.endswith("/prompt"):
            return {"data": {"id": "inbox"}}
        if path == "/session/active":
            return {"data": {}}
        if "/message?" in path:
            return {"data": messages(self.pie, self.answer),
                    "cursor": {"next": "next"}}
        raise AssertionError((method, path))


class PairedBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.questions = [
            {"id": "q1", "question": "Which function reads the index?",
             "gold": "command_status"},
            {"id": "q2", "question": "Which function reads the index again?",
             "gold": "command_status"},
        ]

    def test_pair_is_measured_without_inventing_tokens(self):
        result = run(Fake(self.root, True), Fake(self.root, False),
                     self.root, "opencode/test-model", self.questions, 5)
        summary = result["summary"]
        self.assertTrue(summary["certified"])
        self.assertEqual(summary["token_comparable_pairs"], 2)
        self.assertEqual(summary["with_pie_correct"], 2)
        self.assertEqual(summary["without_pie_correct"], 2)
        self.assertEqual(summary["token_savings_pct"], 76.19)
        self.assertEqual(len(result["rows"]), 2)
        self.assertNotIn("question", result["rows"][0])

    def test_with_pie_missing_real_tool_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "PIE tool"):
            _parse_final(messages(False, "command_status"), True)

    def test_without_pie_connected_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "still exposes pie"):
            run(Fake(self.root, True), Fake(self.root, True),
                self.root, "opencode/test-model", self.questions, 5)

    def test_missing_metrics_never_implies_savings(self):
        rows = [{"with_pie": {"status": "COMPLETED",
                             "correct": True, "tokens": {"input": 10}},
                 "without_pie": {"status": "COMPLETED",
                                 "correct": True, "tokens": {"input": 50}}}]
        summary = summarize(rows)
        self.assertEqual(summary["token_comparable_pairs"], 0)
        self.assertIsNone(summary["token_savings_pct"])
        self.assertFalse(summary["certified"])

    def test_invalid_gold_data_rejected(self):
        file = self.root / "questions.json"
        file.write_text(json.dumps([{"id": "1", "question": "x", "gold": "a"},
                                   {"id": "1", "question": "y", "gold": "b"}]))
        with self.assertRaisesRegex(ValueError, "Invalid"):
            load_questions(file)

    def test_doctor_mesh_cannot_spoof_pie_proof(self):
        transcript = messages(True, "command_status")
        transcript[1]["content"][0]["name"] = "pie_doctor_mesh_pie_project_status"
        with self.assertRaisesRegex(RuntimeError, "PIE tool"):
            _parse_final(transcript, True)

    def test_baseline_using_another_mcp_is_rejected(self):
        transcript = messages(False, "command_status")
        transcript[1]["content"] = [{
            "type": "tool", "name": "9remote_lookup",
            "state": {"status": "completed", "content": ["x"]}
        }]
        with self.assertRaisesRegex(RuntimeError, "unapproved tool"):
            _parse_final(transcript, False)

    def test_partial_transcript_is_not_completion(self):
        incomplete = messages(True, "command_status")[:-1]
        with self.assertRaisesRegex(RuntimeError, "idle"):
            _parse_final(incomplete, True)


if __name__ == "__main__":
    unittest.main()
