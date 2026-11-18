from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pie.web import (
    AccessibilityNode,
    SnapshotNormalizer,
    ActionExecutor,
    DriverOutcome,
    ExecutionState,
    WebIntelligenceService,
    WebStateError,
)
from pie.runtime.replay import ExecutionJournal


def _snapshot():
    return SnapshotNormalizer().normalize(
        session_id="s1", page_id="p1", frame_id="main", generation=1,
        origin="https://example.test", path="/", title="Home",
        tree=AccessibilityNode(role="main", name="Home", children=(AccessibilityNode(role="button", name="Open", region="main"),)),
        captured_at="2026-01-01T00:00:00Z",
    ).snapshot


class _Driver:
    def execute(self, plan, input_value=None):
        return DriverOutcome(ExecutionState.COMPLETED, "snap-2", "p1", None)


class IntegrationTests(unittest.TestCase):
    def test_capability_registry_separates_read_plan_and_execute(self):
        names = {item["name"]: item for item in WebIntelligenceService.capabilities()}
        self.assertFalse(names["pie_web_observe"]["execution"])
        self.assertFalse(names["pie_web_plan"]["execution"])
        self.assertTrue(names["pie_web_execute"]["execution"])

    def test_context_pipeline_returns_non_authorizing_pack(self):
        pack = WebIntelligenceService().context(_snapshot(), "open")
        self.assertFalse(pack.execution_authorized)
        self.assertEqual(pack.provenance.snapshot_id, _snapshot().snapshot_id)

    def test_observation_is_bounded_and_has_no_actions(self):
        observed = WebIntelligenceService().observe(_snapshot())
        self.assertEqual(observed["execution_authorized"], False)
        self.assertNotIn("accessible_name", observed)

    def test_execution_requires_explicit_driver_registration(self):
        service = WebIntelligenceService()
        with self.assertRaisesRegex(WebStateError, "action_driver_unconfigured"):
            service.execute(None)

    def test_journal_requires_an_explicit_executor(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ExecutionJournal(Path(directory) / "actions.sqlite3")
            with self.assertRaisesRegex(WebStateError, "existing action executor"):
                WebIntelligenceService(journal=journal)
            journal.close()

    def test_journal_is_attached_without_creating_storage_implicitly(self):
        executor = ActionExecutor(_Driver())
        with tempfile.TemporaryDirectory() as directory:
            journal = ExecutionJournal(Path(directory) / "actions.sqlite3")
            service = WebIntelligenceService(executor=executor, journal=journal)
            self.assertIsNot(service.executor, executor)
            self.assertIs(service.executor.driver, executor.driver)
            self.assertIs(service.executor.preflight, executor.preflight)
            self.assertIs(service.executor.verifier, executor.verifier)
            self.assertIs(service.executor.journal, journal)
            journal.close()

    def test_same_journal_preserves_existing_executor(self):
        executor = ActionExecutor(_Driver())
        with tempfile.TemporaryDirectory() as directory:
            journal = ExecutionJournal(Path(directory) / "actions.sqlite3")
            executor.journal = journal
            service = WebIntelligenceService(executor=executor, journal=journal)
            self.assertIs(service.executor, executor)
            journal.close()

    def test_different_journal_is_rejected(self):
        executor = ActionExecutor(_Driver())
        with tempfile.TemporaryDirectory() as directory:
            first = ExecutionJournal(Path(directory) / "first.sqlite3")
            second = ExecutionJournal(Path(directory) / "second.sqlite3")
            executor.journal = first
            with self.assertRaisesRegex(WebStateError, "different journal"):
                WebIntelligenceService(executor=executor, journal=second)
            first.close()
            second.close()


if __name__ == "__main__":
    unittest.main()
