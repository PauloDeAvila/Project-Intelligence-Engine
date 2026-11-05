import pathlib
import sys
import unittest
import math
import os
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pie.web import (  # noqa: E402
    ActionResult,
    ActionStatus,
    BrowserSession,
    ElementCandidate,
    ElementReference,
    ExecutionState,
    PageSnapshot,
    ReferenceState,
    SessionState,
    SnapshotState,
    TaskIntent,
    VerificationState,
    WebMetric,
    WebStateError,
    normalize_origin,
)


class WebContractTests(unittest.TestCase):
    def _element(
        self, ref="e1", snapshot_id="snap1", page_id="p1", generation=3,
        snapshot_sha256="a" * 64, role="button", source="accessibility_tree",
        available_actions=("click", "click"),
    ):
        return ElementCandidate(
            ref=ref,
            session_id="s1",
            snapshot_id=snapshot_id,
            page_id=page_id,
            generation=generation,
            snapshot_sha256=snapshot_sha256,
            role=role,
            accessible_name="Continue",
            frame_id="main",
            source=source,
            available_actions=available_actions,
        )

    def test_phase_zero_imports_without_browser_or_network(self):
        session = BrowserSession(
            session_id="s1",
            adapter="playwright",
            allowed_origins=("https://example.test",),
        )
        self.assertEqual(session.state, SessionState.NEW)
        self.assertTrue(session.allows("https://example.test/path"))
        self.assertFalse(session.allows("https://other.test/path"))

    def test_web_import_keeps_browser_subsystem_lazy(self):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import pie.web; print('pie.web.browser' in sys.modules); print('playwright' in sys.modules)",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(probe.stdout.splitlines(), ["False", "False"])

    def test_origin_policy_is_exact_and_rejects_credentials(self):
        self.assertEqual(normalize_origin("HTTPS://Example.test:443/path"), "https://example.test")
        with self.assertRaises(WebStateError):
            BrowserSession(
                session_id="s1",
                adapter="playwright",
                allowed_origins=("https://user:secret@example.test",),
            )
        with self.assertRaises(WebStateError):
            BrowserSession(
                session_id="s1",
                adapter="playwright",
                allowed_origins=("https://example.test/path",),
            )
        with self.assertRaises(WebStateError):
            normalize_origin("file:///C:/private.txt")
        with self.assertRaises(WebStateError):
            normalize_origin("https://*.example.test")
        with self.assertRaises(WebStateError):
            normalize_origin("https://@example.test")
        with self.assertRaises(WebStateError):
            normalize_origin("https://bad host/")
        with self.assertRaises(WebStateError):
            normalize_origin("https://%65xample.test/")
        with self.assertRaises(WebStateError):
            normalize_origin("https://exa^mple.test/")
        with self.assertRaises(WebStateError):
            normalize_origin("https://[2001:db8:::1]/")
        with self.assertRaises(WebStateError):
            normalize_origin("https://[v1.foo]/")
        with self.assertRaises(WebStateError):
            normalize_origin("https://0177.0.0.1/")
        self.assertEqual(normalize_origin("https://127.0.0.1/"), "https://127.0.0.1")
        with self.assertRaises(WebStateError):
            normalize_origin("https://127.1/")
        with self.assertRaises(WebStateError):
            normalize_origin("https://2130706433/")
        with self.assertRaises(WebStateError):
            normalize_origin("https://0x7f000001/")
        with self.assertRaises(WebStateError):
            normalize_origin("https://foo.123/")
        with self.assertRaises(WebStateError):
            normalize_origin("https://0x/")
        with self.assertRaises(WebStateError):
            normalize_origin("https://foo.0x/")
        self.assertEqual(normalize_origin("https://0xford.example/"), "https://0xford.example")
        with self.assertRaises(WebStateError):
            normalize_origin("https://127.0.0.1./")
        with self.assertRaises(WebStateError):
            normalize_origin("https://foo..example/")
        with self.assertRaises(WebStateError):
            normalize_origin("https://-bad.example/")
        self.assertEqual(normalize_origin("https://dead.beef/"), "https://dead.beef")
        self.assertEqual(normalize_origin("https://3d.cafe/"), "https://3d.cafe")
        self.assertNotEqual(
            normalize_origin("https://[2001:db8::1]:1234"),
            normalize_origin("https://[2001:db8::1:1234]"),
        )
        self.assertEqual(
            normalize_origin("https://[2001:db8::1]:1234"),
            normalize_origin("https://[2001:0db8:0:0:0:0:0:1]:1234"),
        )

    def test_session_lifecycle_fails_closed(self):
        session = BrowserSession(session_id="s1", adapter="playwright")
        connecting = session.transition(SessionState.CONNECTING)
        connected = connecting.transition(SessionState.READY, page_id="p1", generation=1)
        closed = connected.transition(SessionState.CLOSED)
        self.assertEqual(closed.state, SessionState.CLOSED)
        with self.assertRaises(WebStateError):
            closed.transition(SessionState.READY, page_id="p2")
        with self.assertRaises(WebStateError):
            session.transition(SessionState.READY)
        with self.assertRaises(WebStateError):
            connected.transition(SessionState.DEGRADED, generation=0)
        failed = connected.transition(SessionState.FAILED)
        with self.assertRaises(WebStateError):
            failed.transition(SessionState.READY, page_id="p2")
        with self.assertRaises(WebStateError):
            failed.transition(SessionState.CONNECTING, page_id="p2", generation=1)
        with self.assertRaises(WebStateError):
            failed.transition(SessionState.CONNECTING, page_id="", generation=2)
        with self.assertRaises(WebStateError):
            failed.transition(SessionState.CONNECTING, page_id="p2", generation="2")
        self.assertEqual(
            failed.transition(SessionState.CONNECTING, page_id="p2", generation=2).state,
            SessionState.CONNECTING,
        )
        with self.assertRaises(WebStateError):
            connected.transition(SessionState.DEGRADED).transition(SessionState.CONNECTING)
        with self.assertRaises(WebStateError):
            BrowserSession(session_id="s2", adapter="playwright", state=SessionState.READY)

    def test_page_snapshot_owns_references_and_serializes_deterministically(self):
        element = self._element()
        snapshot = PageSnapshot(
            snapshot_id="snap1",
            session_id="s1",
            page_id="p1",
            frame_id="main",
            generation=3,
            state=SnapshotState.CURRENT,
            origin="https://example.test",
            path="/checkout",
            title="Checkout",
            snapshot_sha256="a" * 64,
            elements=(element,),
        )
        self.assertEqual(snapshot.find("e1"), element)
        self.assertEqual(element.available_actions, ("click",))
        self.assertEqual(snapshot.to_json(), snapshot.to_json())
        self.assertEqual(snapshot.to_dict()["schema"], "pie-web-contracts-v1")

    def test_snapshot_rejects_duplicate_or_foreign_elements(self):
        with self.assertRaises(WebStateError):
            PageSnapshot(
                "snap1", "s1", "p1", "main", 3, SnapshotState.CURRENT,
                "https://example.test", "/", "Home", "a" * 64,
                (self._element(), self._element()),
            )
        with self.assertRaises(WebStateError):
            PageSnapshot(
                "snap1", "s1", "p1", "main", 3, SnapshotState.CURRENT,
                "https://example.test", "/", "Home", "a" * 64,
                (self._element(snapshot_id="other"),),
            )
        with self.assertRaises(WebStateError):
            PageSnapshot(
                "snap1", "s1", "p1", "main", 3, SnapshotState.CURRENT,
                "https://example.test", "/search?token=secret", "Home", "a" * 64,
                (self._element(),),
            )

        with self.assertRaises(WebStateError):
            self._element(role="SYNTHETIC-ROLE")
        with self.assertRaises(WebStateError):
            self._element(source="synthetic-source")
        with self.assertRaises(WebStateError):
            self._element(available_actions=("eval",))
        self.assertEqual(self._element(available_actions=("CLICK",)).available_actions, ("click",))
        with self.assertRaises(WebStateError):
            self._element(ref="bad\ud800ref")

    def test_non_current_snapshot_downgrades_references(self):
        stale = PageSnapshot(
            "snap1", "s1", "p1", "main", 3, SnapshotState.STALE,
            "https://example.test", "/", "Home", "a" * 64, (self._element(),),
        )
        blocked = PageSnapshot(
            "snap2", "s1", "p1", "main", 3, SnapshotState.BLOCKED,
            "https://example.test", "/", "Home", "b" * 64,
            (self._element(snapshot_id="snap2", snapshot_sha256="b" * 64),),
        )
        self.assertEqual(stale.find("e1").reference.state, ReferenceState.STALE)
        self.assertEqual(blocked.find("e1").reference.state, ReferenceState.UNKNOWN)

    def test_stale_reference_is_explicit_not_silently_current(self):
        reference = ElementReference(
            "e1", "s1", "p1", "main", "snap1", "a" * 64, 1, ReferenceState.STALE
        )
        self.assertEqual(reference.state, ReferenceState.STALE)

    def test_intent_contains_goal_not_executable_selector(self):
        intent = TaskIntent(
            intent_id="i1",
            session_id="s1",
            page_id="p1",
            goal="open the settings area",
            target_query="settings",
            expected_transition="settings-panel-visible",
        )
        self.assertEqual(intent.goal, "open the settings area")
        self.assertEqual(
            TaskIntent("i2", "s1", "p1", "click css selector=#submit").goal,
            "click css selector=#submit",
        )
        self.assertEqual(
            TaskIntent("i3", "s1", "p1", "run javascript: alert(1)").goal,
            "run javascript: alert(1)",
        )
        self.assertEqual(
            TaskIntent("i4", "s1", "p1", "use password=secret").goal,
            "use password=secret",
        )
        with self.assertRaises(WebStateError):
            TaskIntent("i5", "s1", "p1", "bad\x00value")
        with self.assertRaises(WebStateError):
            TaskIntent("i5-surrogate", "s1", "p1", "bad\ud800value")
        self.assertEqual(
            TaskIntent("i6", "s1", "p1", "click at coordinates x=10 y=20").goal,
            "click at coordinates x=10 y=20",
        )
        self.assertEqual(
            TaskIntent("i7", "s1", "p1", "find the submit control", target_query="#submit").target_query,
            "#submit",
        )
        self.assertEqual(
            TaskIntent("i8-literal", "s1", "p1", "find the submit control", target_query="button.primary").target_query,
            "button.primary",
        )
        with self.assertRaises(WebStateError):
            TaskIntent("i8", "s1", "p1", "find the submit control", action="eval(alert(1))")
        self.assertEqual(
            TaskIntent("i9", "s1", "p1", "find the save control", target_query="Salvar e sair?").target_query,
            "Salvar e sair?",
        )
        self.assertEqual(
            TaskIntent("i10", "s1", "p1", "find Configurações", target_query="Configurações v2.1").target_query,
            "Configurações v2.1",
        )
        self.assertEqual(TaskIntent("i10-action", "s1", "p1", "click", action="CLICK").action, "click")
        self.assertEqual(TaskIntent("i11", "s1", "p1", "alert(1)").goal, "alert(1)")
        with self.assertRaises(WebStateError):
            TaskIntent("i12", "s1", "p1", "find it", expected_transition="location.assign('https://other.test')")

    def test_serialization_redacts_sensitive_page_text(self):
        element = ElementCandidate(
            ref="e1",
            session_id="s1",
            snapshot_id="snap1",
            page_id="p1",
            generation=3,
            snapshot_sha256="a" * 64,
            role="text",
            accessible_name="password=secret-value",
        )
        serialized = PageSnapshot(
            "snap1", "s1", "p1", "main", 3, SnapshotState.CURRENT,
            "https://example.test", "/", "Home", "a" * 64, (element,),
        ).to_json()
        self.assertNotIn("secret-value", serialized)
        self.assertIn("[REDACTED_PAGE_DATA]", serialized)
        self.assertNotIn("SYNTHETIC-ABC", PageSnapshot(
            "snap1", "s1", "p1", "main", 3, SnapshotState.CURRENT,
            "https://example.test", "/reset/SYNTHETIC-ABC", "Authorization: Basic SYNTHETIC-ABC", "a" * 64,
        ).to_json())
        self.assertNotIn("Ab7Df9VtQ", PageSnapshot(
            "snap1", "s1", "p1", "main", 3, SnapshotState.CURRENT,
            "https://example.test", "/reset/Ab7Df9VtQ", "Home", "a" * 64,
        ).to_json())
        self.assertNotIn("GxVaTpQz", PageSnapshot(
            "snap1", "s1", "p1", "main", 3, SnapshotState.CURRENT,
            "https://example.test", "/reset/GxVaTpQz", "Home", "a" * 64,
        ).to_json())
        self.assertNotIn("84739261", PageSnapshot(
            "snap1", "s1", "p1", "main", 3, SnapshotState.CURRENT,
            "https://example.test", "/reset/84739261", "Home", "a" * 64,
        ).to_json())
        self.assertNotIn("%41%62%63", PageSnapshot(
            "snap1", "s1", "p1", "main", 3, SnapshotState.CURRENT,
            "https://example.test", "/reset/%41%62%63", "Home", "a" * 64,
        ).to_json())
        self.assertNotIn("SEGREDO SINTÉTICO", PageSnapshot(
            "snap1", "s1", "p1", "main", 3, SnapshotState.CURRENT,
            "https://example.test", "/", '{"password": "SEGREDO SINTÉTICO"}', "a" * 64,
        ).to_json())
        self.assertNotIn("SYNTHETIC-PROBE", PageSnapshot(
            "snap1", "s1", "p1", "main", 3, SnapshotState.CURRENT,
            "https://example.test", "/", '{\\\"password\\\": \\\"SYNTHETIC-PROBE\\\"}', "a" * 64,
        ).to_json())
        self.assertNotIn("two words", PageSnapshot(
            "snap1", "s1", "p1", "main", 3, SnapshotState.CURRENT,
            "https://example.test", "/", 'password="two words"', "a" * 64,
        ).to_json())
        self.assertNotIn("sample two words", ElementCandidate(
            ref="e1", session_id="s1", snapshot_id="snap1", page_id="p1", generation=3,
            snapshot_sha256="a" * 64, role="text", accessible_name='{"password": "sample two words"}',
        ).to_json())

    def test_action_result_requires_verified_success(self):
        with self.assertRaises(WebStateError):
            ActionResult(
                "a1", "i1", ActionStatus.SUCCEEDED,
                ExecutionState.COMPLETED, VerificationState.NOT_RUN,
                "s1", "p1", "snap1",
            )
        with self.assertRaises(WebStateError):
            ActionResult(
                "a2", "i1", ActionStatus.BLOCKED,
                ExecutionState.NOT_STARTED, VerificationState.NOT_RUN,
                "s1", "p1", "snap1",
            )
        with self.assertRaises(WebStateError):
            ActionResult(
                "a-timeout", "i1", ActionStatus.TIMEOUT,
                ExecutionState.COMPLETED, VerificationState.NOT_RUN,
                "s1", "p1", "snap1", error_code="timeout",
            )
        with self.assertRaises(WebStateError):
            ActionResult(
                "a-failed", "i1", ActionStatus.FAILED,
                ExecutionState.COMPLETED, VerificationState.VERIFIED,
                "s1", "p1", "snap1", error_code="execution_failed",
            )
        with self.assertRaises(WebStateError):
            ActionResult(
                "a-planned", "i1", ActionStatus.PLANNED,
                ExecutionState.STARTED, VerificationState.NOT_RUN,
                "s1", "p1", "snap1",
            )
        with self.assertRaises(WebStateError):
            ActionResult(
                "a-blocked", "i1", ActionStatus.BLOCKED,
                ExecutionState.STARTED, VerificationState.NOT_RUN,
                "s1", "p1", "snap1", error_code="action_blocked",
            )
        with self.assertRaises(WebStateError):
            ActionResult(
                "a-failed-complete", "i1", ActionStatus.FAILED,
                ExecutionState.COMPLETED, VerificationState.NOT_RUN,
                "s1", "p1", "snap1", error_code="execution_failed",
            )
        with self.assertRaises(WebStateError):
            ActionResult(
                "a-success-error", "i1", ActionStatus.SUCCEEDED,
                ExecutionState.COMPLETED, VerificationState.VERIFIED,
                "s1", "p1", "snap1", error_code="timeout",
            )
        self.assertEqual(
            ActionResult(
                "a-valid-failed", "i1", ActionStatus.FAILED,
                ExecutionState.STARTED, VerificationState.NOT_RUN,
                "s1", "p1", "snap1", error_code="execution_failed",
            ).status,
            ActionStatus.FAILED,
        )
        self.assertEqual(
            ActionResult(
                "a-valid-verification", "i1", ActionStatus.FAILED,
                ExecutionState.COMPLETED, VerificationState.FAILED,
                "s1", "p1", "snap1", error_code="verification_failed",
            ).status,
            ActionStatus.FAILED,
        )
        result = ActionResult(
            "a3", "i1", ActionStatus.SUCCEEDED,
            ExecutionState.COMPLETED, VerificationState.VERIFIED,
            "s1", "p1", "snap1", "snap2", "e1", 2.5, evidence_ids=("ev1",),
        )
        self.assertEqual(result.status, ActionStatus.SUCCEEDED)

    def test_metrics_reject_negative_values(self):
        metric = WebMetric("snapshot", "ok", 2.5, input_tokens=10, output_tokens=4)
        self.assertEqual(metric.input_tokens, 10)
        with self.assertRaises(WebStateError):
            WebMetric("snapshot", "ok", -1)
        with self.assertRaises(WebStateError):
            WebMetric("snapshot", "ok", 1, input_tokens=True)
        with self.assertRaises(WebStateError):
            WebMetric("snapshot", "ok", math.nan)
        with self.assertRaises(WebStateError):
            WebMetric("snapshot", "ok", 1, error_code="secret-value")
        with self.assertRaises(WebStateError):
            WebMetric("secret-operation", "ok", 1)
        with self.assertRaises(WebStateError):
            WebMetric("snapshot", "secret-status", 1)
        with self.assertRaises(WebStateError):
            BrowserSession(session_id="s3", adapter="playwright", created_at=math.inf)
        with self.assertRaises(WebStateError):
            BrowserSession(session_id="s5", adapter="playwright", created_at="SYNTHETIC-TIMESTAMP")
        with self.assertRaises(WebStateError):
            BrowserSession(session_id="s6", adapter="playwright", created_at="2026-11-05X12:34:56+00:00")
        with self.assertRaises(WebStateError):
            BrowserSession(session_id="s7", adapter="playwright", created_at="2026-11-05T12:34:56+00:99")
        with self.assertRaises(WebStateError):
            BrowserSession(session_id="s4", adapter="playwright", generation=10**5000)
        with self.assertRaises(WebStateError):
            WebMetric("snapshot", "ok", 1, input_tokens=10**5000)
        with self.assertRaises(WebStateError):
            PageSnapshot(
                "snap3", "s1", "p1", "main", 3, SnapshotState.CURRENT,
                "https://example.test", "/", "Home", "c" * 64, captured_at=math.nan,
            )
        with self.assertRaises(WebStateError):
            PageSnapshot(
                "snap4", "s1", "p1", "main", 3, SnapshotState.CURRENT,
                "https://example.test", "/", "Home", "c" * 64, captured_at="SYNTHETIC-TIMESTAMP",
            )


if __name__ == "__main__":
    unittest.main()
