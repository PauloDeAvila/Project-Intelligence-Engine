from __future__ import annotations

import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest

from pie.web import (
    BrowserConnector,
    NavigationController,
    PlaywrightBrowserAdapter,
    SnapshotNormalizer,
)


@unittest.skipUnless(importlib.util.find_spec("playwright"), "optional Playwright dependency is not installed")
class PlaywrightSnapshotIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib protocol name
                body = b"""<!doctype html><html><head><title>Fixture</title></head>
                <body><main><form aria-label='Search form'>
                <label>Search <input aria-label='Search field'></label>
                <button aria-label='Search button'>Search</button>
                <div role='custom-widget' aria-label='Unsupported widget'></div>
                </form></main></body></html>"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.adapter = PlaywrightBrowserAdapter(headless=True, timeout_ms=15_000)
        self.connector = BrowserConnector()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"
        self.connector.create_session(
            session_id="snapshot-session",
            adapter=self.adapter,
            adapter_name="playwright",
            allowed_origins=(self.origin,),
        )

    def tearDown(self) -> None:
        try:
            self.connector.close("snapshot-session")
        except Exception:
            pass
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_real_page_is_reduced_to_normalized_candidates(self):
        connected = self.connector.connect("snapshot-session")
        result = NavigationController(self.connector).navigate(
            "snapshot-session", f"{self.origin}/fixture"
        )
        extracted = self.connector.extract_page_tree(
            "snapshot-session",
            page_id=result.session.current_page_id,
            frame_id="main",
            max_elements=32,
        )
        snapshot = SnapshotNormalizer().normalize(
            session_id="snapshot-session",
            page_id=result.session.current_page_id or connected.session.current_page_id or "page",
            frame_id="main",
            generation=result.session.generation,
            origin=result.page.origin or self.origin,
            path=result.page.path or "/",
            title="Fixture",
            tree=extracted.tree,
        ).snapshot
        names = {item.accessible_name for item in snapshot.elements}
        roles = {item.role for item in snapshot.elements}
        self.assertIn("Search field", names)
        self.assertIn("Search button", names)
        self.assertIn("input", roles)
        self.assertIn("button", roles)
        self.assertTrue(all(item.source == "dom_snapshot" for item in snapshot.elements))
        self.assertGreaterEqual(len(snapshot.elements), 4)


if __name__ == "__main__":
    unittest.main()
