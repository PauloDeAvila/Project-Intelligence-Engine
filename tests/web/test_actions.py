from __future__ import annotations

from dataclasses import replace
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


if __name__ == "__main__":
    unittest.main()
