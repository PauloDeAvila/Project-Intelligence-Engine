from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest

from pie.web import (
    ActionExecutor,
    ActionPlanner,
    ActionStatus,
    BrowserSession,
    ContentTrust,
    DriverOutcome,
    ElementCandidate,
    ExecutionState,
    PageSnapshot,
    PreflightValidator,
    RecoveryAction,
    RecoveryController,
    SecurityGate,
    SessionState,
    SnapshotState,
    TaskIntent,
)
from pie.runtime.replay import ExecutionJournal, ReplayConflict


SHA = "b" * 64


def _session() -> BrowserSession:
    return BrowserSession("s1", "test", state=SessionState.CONNECTING, allowed_origins=("https://example.test",)).transition(
        SessionState.READY, page_id="p1", generation=1
    )


def _candidate() -> ElementCandidate:
    return ElementCandidate(
        ref="ref-1", session_id="s1", snapshot_id="snap-1", page_id="p1", generation=1,
        snapshot_sha256=SHA, role="button", accessible_name="Open", available_actions=("click",),
        content_trust=ContentTrust.UNTRUSTED_PAGE_DATA,
    )


def _snapshot() -> PageSnapshot:
    return PageSnapshot(
        "snap-1", "s1", "p1", "main", 1, SnapshotState.CURRENT, "https://example.test", "/", "Home", SHA,
        (_candidate(),),
    )


class _Driver:
    def __init__(self, outcome: DriverOutcome):
        self.outcome = outcome
        self.calls = 0

    def execute(self, plan, input_value=None):
        self.calls += 1
        return self.outcome


class _BlockingDriver(_Driver):
    def __init__(self, outcome: DriverOutcome):
        super().__init__(outcome)
        self.started = threading.Event()
        self.release = threading.Event()

    def execute(self, plan, input_value=None):
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=5)
        return self.outcome


def _approved_action(action_id: str = "a1"):
    session = _session()
    snapshot = _snapshot()
    intent = TaskIntent("i1", "s1", "p1", "open", action="click")
    security = SecurityGate()
    plan = ActionPlanner(security=security).plan(
        action_id=action_id, session=session, snapshot=snapshot, intent=intent, candidate=_candidate()
    )
    decision = security.authorize(session, snapshot, intent, _candidate())
    request = security.request_approval(decision)
    security.approvals.approve(request.request_id)
    validator = PreflightValidator(security=security)
    return plan, session, snapshot, intent, request.request_id, validator, security


def _approve_again(security: SecurityGate, session: BrowserSession, snapshot: PageSnapshot, intent: TaskIntent) -> str:
    decision = security.authorize(session, snapshot, intent, _candidate())
    request = security.request_approval(decision)
    security.approvals.approve(request.request_id)
    return request.request_id


class ActionEngineTests(unittest.TestCase):
    def test_preflight_approval_and_post_verification(self):
        session = _session()
        snapshot = _snapshot()
        intent = TaskIntent("i1", "s1", "p1", "open", action="click")
        security = SecurityGate()
        planner = ActionPlanner(security=security)
        plan = planner.plan(action_id="a1", session=session, snapshot=snapshot, intent=intent, candidate=_candidate())
        decision = security.authorize(session, snapshot, intent, _candidate())
        request = security.request_approval(decision)
        security.approvals.approve(request.request_id)
        driver = _Driver(DriverOutcome(ExecutionState.COMPLETED, "snap-2", "p1", None, 4.0))
        result = ActionExecutor(driver, preflight=PreflightValidator(security=security)).execute(
            plan, session=session, before=snapshot, intent=intent, candidate=_candidate(), approval_id=request.request_id
        )
        self.assertEqual(result.status, ActionStatus.SUCCEEDED)
        self.assertEqual(driver.calls, 1)

    def test_failed_verification_is_not_success(self):
        session = _session()
        snapshot = _snapshot()
        intent = TaskIntent("i1", "s1", "p1", "open", action="navigate")
        security = SecurityGate()
        plan = ActionPlanner(security=security).plan(
            action_id="a1", session=session, snapshot=snapshot, intent=intent, target_url="https://example.test/next"
        )
        driver = _Driver(DriverOutcome(ExecutionState.COMPLETED, "snap-1", "p1", None))
        result = ActionExecutor(driver, preflight=PreflightValidator(security=security)).execute(
            plan, session=session, before=snapshot, intent=intent, target_url="https://example.test/next"
        )
        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertEqual(result.error_code, "verification_failed")

    def test_stale_plan_is_not_executed_and_recovery_does_not_retry(self):
        session = _session()
        snapshot = _snapshot()
        intent = TaskIntent("i1", "s1", "p1", "open", action="navigate")
        security = SecurityGate()
        plan = ActionPlanner(security=security).plan(
            action_id="a1", session=session, snapshot=snapshot, intent=intent, target_url="https://example.test/next"
        )
        newer = replace(snapshot, snapshot_id="snap-2", snapshot_sha256="c" * 64, elements=())
        driver = _Driver(DriverOutcome(ExecutionState.COMPLETED, "snap-3", "p1", "done"))
        result = ActionExecutor(driver, preflight=PreflightValidator(security=security)).execute(
            plan, session=session, before=newer, intent=intent, target_url="https://example.test/next"
        )
        recovery = RecoveryController().recover(plan, result)
        self.assertEqual(result.status, ActionStatus.STALE)
        self.assertEqual(recovery.action, RecoveryAction.REFRESH_SNAPSHOT)
        self.assertFalse(recovery.automatic_retry)
        self.assertEqual(driver.calls, 0)

    def test_journal_replays_safe_action_result_without_driver(self):
        plan, session, snapshot, intent, approval_id, validator, security = _approved_action()
        driver = _Driver(DriverOutcome(ExecutionState.COMPLETED, "snap-2", "p1", None, 4.0))
        with tempfile.TemporaryDirectory() as directory:
            journal = ExecutionJournal(Path(directory) / "actions.sqlite3")
            executor = ActionExecutor(driver, preflight=validator, journal=journal)
            first = executor.execute(
                plan, session=session, before=snapshot, intent=intent,
                candidate=_candidate(), approval_id=approval_id, input_value="safe-input",
            )
            duplicate = executor.execute(
                plan, session=session, before=snapshot, intent=intent,
                candidate=_candidate(), approval_id=_approve_again(security, session, snapshot, intent), input_value="safe-input",
            )
            self.assertEqual(first, duplicate)
            self.assertEqual(first.status, ActionStatus.SUCCEEDED)
            self.assertEqual(driver.calls, 1)
            row = journal._connection.execute(
                "SELECT result_metadata_json FROM execution_journal"
            ).fetchone()
            self.assertNotIn("safe-input", row[0])
            journal.close()

    def test_journal_conflict_does_not_execute_again(self):
        plan, session, snapshot, intent, approval_id, validator, security = _approved_action()
        driver = _Driver(DriverOutcome(ExecutionState.COMPLETED, "snap-2", "p1", None, 4.0))
        with tempfile.TemporaryDirectory() as directory:
            journal = ExecutionJournal(Path(directory) / "actions.sqlite3")
            executor = ActionExecutor(driver, preflight=validator, journal=journal)
            executor.execute(
                plan, session=session, before=snapshot, intent=intent,
                candidate=_candidate(), approval_id=approval_id, input_value="first",
            )
            with self.assertRaises(ReplayConflict):
                executor.execute(
                    plan, session=session, before=snapshot, intent=intent,
                    candidate=_candidate(), approval_id=_approve_again(security, session, snapshot, intent), input_value="second",
                )
            self.assertEqual(driver.calls, 1)
            journal.close()

    def test_started_journal_entry_requires_reconciliation(self):
        plan, session, snapshot, intent, approval_id, validator, security = _approved_action()
        driver = _BlockingDriver(DriverOutcome(ExecutionState.COMPLETED, "snap-2", "p1", None, 4.0))
        with tempfile.TemporaryDirectory() as directory:
            journal = ExecutionJournal(Path(directory) / "actions.sqlite3")
            executor = ActionExecutor(driver, preflight=validator, journal=journal)
            first_result = []
            worker = threading.Thread(
                target=lambda: first_result.append(executor.execute(
                    plan, session=session, before=snapshot, intent=intent,
                    candidate=_candidate(), approval_id=approval_id,
                ))
            )
            worker.start()
            self.assertTrue(driver.started.wait(timeout=2))
            second = executor.execute(
                plan, session=session, before=snapshot, intent=intent,
                candidate=_candidate(), approval_id=_approve_again(security, session, snapshot, intent),
            )
            self.assertEqual(second.error_code, "reconciliation_required")
            self.assertEqual(driver.calls, 1)
            driver.release.set()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(first_result[0].status, ActionStatus.SUCCEEDED)
            journal.close()


if __name__ == "__main__":
    unittest.main()
