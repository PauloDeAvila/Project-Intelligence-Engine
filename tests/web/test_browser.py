from __future__ import annotations

import unittest

from pie.web import (
    BrowserConnector,
    BrowserConnectorError,
    BrowserHealthMonitor,
    BrowserPage,
    NavigationController,
    PlaywrightBrowserAdapter,
    SessionState,
    WebStateError,
)
from pie.web.browser.adapter import BrowserAdapterError, BrowserFrame


class FakeAdapter:
    def __init__(self) -> None:
        self.connected = False
        self.healthy = True
        self.navigations: list[str] = []
        self._page = BrowserPage("page-1", "main", "https://allowed.test/home?secret=hidden")

    def connect(self) -> None:
        if self.connected:
            raise BrowserAdapterError("adapter_already_connected")
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def pages(self) -> tuple[BrowserPage, ...]:
        if not self.connected:
            raise BrowserAdapterError("adapter_not_connected")
        return (self._page,)

    def frames(self) -> tuple[BrowserFrame, ...]:
        if not self.connected:
            raise BrowserAdapterError("adapter_not_connected")
        return (BrowserFrame("frame-1", "page-1", self._page.url),)

    def open_page(self) -> BrowserPage:
        if not self.connected:
            raise BrowserAdapterError("adapter_not_connected")
        return self._page

    def navigate(self, url: str) -> BrowserPage:
        if not self.connected:
            raise BrowserAdapterError("adapter_not_connected")
        self.navigations.append(url)
        self._page = BrowserPage("page-1", "main", url)
        return self._page

    def health_check(self) -> bool:
        if not self.connected:
            raise BrowserAdapterError("adapter_not_connected")
        return self.healthy


class FailingAdapter(FakeAdapter):
    def connect(self) -> None:
        raise BrowserAdapterError("adapter_connect_failed")


class RedirectingAdapter(FakeAdapter):
    def navigate(self, url: str) -> BrowserPage:
        if not self.connected:
            raise BrowserAdapterError("adapter_not_connected")
        self.navigations.append(url)
        self._page = BrowserPage("page-1", "main", "https://blocked.test/redirected")
        return self._page


class MismatchingAdapter(FakeAdapter):
    def navigate(self, url: str) -> BrowserPage:
        if not self.connected:
            raise BrowserAdapterError("adapter_not_connected")
        self.navigations.append(url)
        return BrowserPage("foreign-page", "main", url)


class BrowserConnectorTests(unittest.TestCase):
    def make_connector(self, adapter: FakeAdapter | None = None):
        connector = BrowserConnector()
        adapter = adapter or FakeAdapter()
        connector.create_session(
            session_id="session-1",
            adapter=adapter,
            adapter_name="fake",
            allowed_origins=("https://allowed.test",),
        )
        return connector, adapter

    def test_connect_redacts_query_and_creates_fresh_generation(self):
        connector, _ = self.make_connector()

        result = connector.connect("session-1")

        self.assertEqual(result.session.state, SessionState.READY)
        self.assertEqual(result.session.generation, 1)
        self.assertEqual(result.page.origin, "https://allowed.test")
        self.assertEqual(result.page.path, "/home")
        self.assertEqual(len(result.pages), 1)
        self.assertEqual(len(result.frames), 1)
        self.assertTrue(result.frames[0].allowed)

    def test_navigation_requires_exact_allowed_origin_and_advances_generation(self):
        connector, adapter = self.make_connector()
        connector.connect("session-1")
        navigation = NavigationController(connector)

        result = navigation.navigate("session-1", "https://allowed.test/results?q=private")

        self.assertEqual(result.session.generation, 2)
        self.assertEqual(result.page.path, "/results")
        self.assertEqual(adapter.navigations, ["https://allowed.test/results?q=private"])
        with self.assertRaisesRegex(BrowserConnectorError, "origin_not_allowed"):
            navigation.navigate("session-1", "https://other.test/results")
        self.assertEqual(len(adapter.navigations), 1)

    def test_health_failure_marks_session_degraded_without_auto_reconnect(self):
        connector, adapter = self.make_connector()
        connector.connect("session-1")
        adapter.healthy = False
        monitor = BrowserHealthMonitor(connector)

        result = monitor.check("session-1")

        self.assertFalse(result.healthy)
        self.assertEqual(result.state, SessionState.DEGRADED)
        self.assertEqual(connector.session("session-1").state, SessionState.DEGRADED)

    def test_redirect_to_disallowed_origin_is_rejected_after_adapter_returns(self):
        connector, adapter = self.make_connector(RedirectingAdapter())
        connector.connect("session-1")
        navigation = NavigationController(connector)

        with self.assertRaisesRegex(BrowserConnectorError, "origin_not_allowed"):
            navigation.navigate("session-1", "https://allowed.test/start")

        self.assertEqual(len(adapter.navigations), 1)
        self.assertEqual(connector.session("session-1").state, SessionState.DEGRADED)

    def test_navigation_requires_page_identity_to_match_current_inventory(self):
        connector, _ = self.make_connector(MismatchingAdapter())
        connector.connect("session-1")
        navigation = NavigationController(connector)

        with self.assertRaisesRegex(BrowserConnectorError, "invalid_page"):
            navigation.navigate("session-1", "https://allowed.test/new")

        self.assertEqual(connector.session("session-1").state, SessionState.DEGRADED)

    def test_reconnect_closes_old_boundary_and_requires_new_observation(self):
        connector, adapter = self.make_connector()
        first = connector.connect("session-1")
        connector.mark_degraded("session-1")

        second = connector.connect("session-1")

        self.assertEqual(second.session.state, SessionState.READY)
        self.assertGreater(second.session.generation, first.session.generation)
        self.assertTrue(adapter.connected)

    def test_failed_connect_is_sanitized_and_session_is_failed(self):
        connector, _ = self.make_connector(FailingAdapter())

        with self.assertRaisesRegex(BrowserConnectorError, "connect_failed"):
            connector.connect("session-1")

        self.assertEqual(connector.session("session-1").state, SessionState.FAILED)

    def test_connect_does_not_expose_existing_page_from_disallowed_origin(self):
        connector, adapter = self.make_connector()
        adapter._page = BrowserPage("page-1", "main", "https://blocked.test/home")

        with self.assertRaisesRegex(BrowserConnectorError, "origin_not_allowed"):
            connector.connect("session-1")

        self.assertEqual(connector.session("session-1").state, SessionState.FAILED)

    def test_closed_session_cannot_be_reused(self):
        connector, _ = self.make_connector()
        connector.connect("session-1")
        connector.close("session-1")

        with self.assertRaisesRegex(BrowserConnectorError, "session_closed"):
            connector.connect("session-1")

    def test_optional_playwright_adapter_does_not_start_on_import_or_construction(self):
        adapter = PlaywrightBrowserAdapter(headless=True)
        self.assertIsNotNone(adapter)

    def test_browser_page_rejects_non_http_pages(self):
        with self.assertRaises(WebStateError):
            BrowserPage("page-1", "main", "javascript:alert(1)")

    def test_same_adapter_cannot_be_owned_by_two_sessions(self):
        connector = BrowserConnector()
        adapter = FakeAdapter()
        connector.create_session(
            session_id="session-1",
            adapter=adapter,
            adapter_name="fake",
            allowed_origins=("https://allowed.test",),
        )
        with self.assertRaisesRegex(BrowserConnectorError, "adapter_already_owned"):
            connector.create_session(
                session_id="session-2",
                adapter=adapter,
                adapter_name="fake",
                allowed_origins=("https://allowed.test",),
            )

    def test_incomplete_adapter_is_rejected_before_session_creation(self):
        connector = BrowserConnector()

        with self.assertRaisesRegex(BrowserConnectorError, "invalid_adapter"):
            connector.create_session(
                session_id="session-1",
                adapter=object(),  # type: ignore[arg-type]
                adapter_name="invalid",
                allowed_origins=("https://allowed.test",),
            )

    def test_cdp_is_disabled_until_isolated_target_contract_exists(self):
        with self.assertRaises(WebStateError):
            PlaywrightBrowserAdapter(cdp_endpoint="http://127.0.0.1:9222")
        with self.assertRaises(WebStateError):
            PlaywrightBrowserAdapter(
                cdp_endpoint="wss://remote-browser.example/ws",
                allow_existing_browser=True,
            )

    def test_sensitive_path_segments_are_redacted(self):
        page = BrowserPage("page-1", "main", "https://allowed.test/reset/SECRET-TOKEN")
        self.assertEqual(page.safe_path, "/[REDACTED]/[REDACTED]")

    def test_arbitrary_navigation_recording_path_is_not_public(self):
        connector, _ = self.make_connector()
        self.assertFalse(hasattr(connector, "record_navigation"))


if __name__ == "__main__":
    unittest.main()
