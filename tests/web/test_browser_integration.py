from __future__ import annotations

import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest

from pie.web import (
    BrowserConnector,
    BrowserConnectorError,
    NavigationController,
    PlaywrightBrowserAdapter,
    SessionState,
)


PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright") is not None


def _handler_for(redirect_target: str):
    class LocalHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib protocol name
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", redirect_target)
                self.end_headers()
                return
            body = b"<html><body><main>local fixture</main></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return LocalHandler


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "optional Playwright dependency is not installed")
class PlaywrightConnectorIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.blocked_server = ThreadingHTTPServer(
            ("127.0.0.1", 0), _handler_for("http://127.0.0.1:1/unused")
        )
        self.blocked_thread = threading.Thread(
            target=self.blocked_server.serve_forever, daemon=True
        )
        self.blocked_thread.start()
        blocked_origin = f"http://127.0.0.1:{self.blocked_server.server_port}"
        self.allowed_server = ThreadingHTTPServer(
            ("127.0.0.1", 0), _handler_for(f"{blocked_origin}/blocked")
        )
        self.allowed_thread = threading.Thread(
            target=self.allowed_server.serve_forever, daemon=True
        )
        self.allowed_thread.start()
        self.adapter = PlaywrightBrowserAdapter(headless=True, timeout_ms=15_000)
        self.connector = BrowserConnector()
        self.connector.create_session(
            session_id="integration-session",
            adapter=self.adapter,
            adapter_name="playwright",
            allowed_origins=(f"http://127.0.0.1:{self.allowed_server.server_port}",),
        )

    def tearDown(self) -> None:
        try:
            self.connector.close("integration-session")
        except Exception:
            pass
        self.allowed_server.shutdown()
        self.blocked_server.shutdown()
        self.allowed_server.server_close()
        self.blocked_server.server_close()
        self.allowed_thread.join(timeout=5)
        self.blocked_thread.join(timeout=5)

    def test_connect_navigate_inventory_and_block_cross_origin_redirect(self):
        connected = self.connector.connect("integration-session")
        self.assertEqual(connected.session.state, SessionState.READY)
        self.assertGreaterEqual(len(connected.pages), 1)
        self.assertGreaterEqual(len(connected.frames), 1)

        navigation = NavigationController(self.connector)
        allowed_url = f"http://127.0.0.1:{self.allowed_server.server_port}/ok"
        result = navigation.navigate("integration-session", allowed_url)
        self.assertEqual(result.page.path, "/ok")
        self.assertEqual(result.session.state, SessionState.READY)

        redirect_url = f"http://127.0.0.1:{self.allowed_server.server_port}/redirect"
        with self.assertRaisesRegex(BrowserConnectorError, "origin_not_allowed"):
            navigation.navigate("integration-session", redirect_url)
        self.assertEqual(
            self.connector.session("integration-session").state,
            SessionState.DEGRADED,
        )


if __name__ == "__main__":
    unittest.main()
