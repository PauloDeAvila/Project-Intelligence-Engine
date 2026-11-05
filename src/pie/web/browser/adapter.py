"""Browser adapter contracts and the optional Playwright implementation.

The web core depends only on the small synchronous adapter protocol in this
module.  Playwright is imported lazily, so code-only PIE installations do not
need a browser package or a browser binary.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

from ..contracts import WebStateError, normalize_origin


_SENSITIVE_PATH_SEGMENT = re.compile(
    r"(?i)(token|secret|password|credential|authorization|bearer|session|nonce|signature|reset|api[_-]?key)"
)
_UUID_OR_HIGH_ENTROPY = re.compile(r"(?i)^(?:[0-9a-f]{16,}|[0-9a-f-]{20,})$")


_ERROR_CODES = frozenset(
    {
        "adapter_unavailable",
        "adapter_not_connected",
        "adapter_already_connected",
        "adapter_connect_failed",
        "adapter_close_failed",
        "adapter_navigation_failed",
        "adapter_health_failed",
        "no_page",
        "invalid_page",
        "origin_not_allowed",
    }
)


class BrowserAdapterError(RuntimeError):
    """A sanitized adapter failure that is safe to expose to orchestration."""

    def __init__(self, code: str):
        if code not in _ERROR_CODES:
            raise ValueError("unknown browser adapter error code")
        self.code = code
        super().__init__(code)


def _bounded_text(value: str, field_name: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise WebStateError(f"{field_name} must be a non-empty bounded string")
    if "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise WebStateError(f"{field_name} contains invalid text")
    return value


def _safe_path(url: str) -> str:
    """Keep benign route shape while redacting secret-like path segments."""

    raw_path = urlsplit(url).path or "/"
    if not raw_path.startswith("/") or "?" in raw_path or "#" in raw_path:
        raise WebStateError("path is not safe")
    safe_segments: list[str] = []
    for segment in raw_path.split("/"):
        if not segment:
            continue
        if (
            len(segment) > 64
            or "%" in segment
            or _SENSITIVE_PATH_SEGMENT.search(segment)
            or _UUID_OR_HIGH_ENTROPY.fullmatch(segment)
            or (segment.isdigit() and len(segment) >= 4)
        ):
            safe_segments.append("[REDACTED]")
        else:
            safe_segments.append(segment)
    return "/" + "/".join(safe_segments)


@dataclass(frozen=True, slots=True)
class BrowserPage:
    """Minimal page identity returned by an adapter.

    The raw URL remains adapter-local.  Callers receive only redacted origin
    and path values through :class:`PageObservation`.
    """

    page_id: str
    frame_id: str
    url: str

    def __post_init__(self) -> None:
        _bounded_text(self.page_id, "page_id")
        _bounded_text(self.frame_id, "frame_id")
        _bounded_text(self.url, "url", 4096)
        if self.url != "about:blank":
            try:
                normalize_origin(self.url)
            except (TypeError, ValueError, WebStateError) as exc:
                raise WebStateError("page url must be http(s) or about:blank") from exc

    @property
    def safe_origin(self) -> str | None:
        if self.url == "about:blank":
            return None
        return normalize_origin(self.url)

    @property
    def safe_path(self) -> str | None:
        if self.url == "about:blank":
            return None
        return _safe_path(self.url)


@dataclass(frozen=True, slots=True)
class BrowserFrame:
    """Minimal frame identity returned by an adapter."""

    frame_id: str
    page_id: str
    url: str

    def __post_init__(self) -> None:
        _bounded_text(self.frame_id, "frame_id")
        _bounded_text(self.page_id, "page_id")
        _bounded_text(self.url, "url", 4096)
        if self.url != "about:blank":
            try:
                normalize_origin(self.url)
            except (TypeError, ValueError, WebStateError) as exc:
                raise WebStateError("frame url must be http(s) or about:blank") from exc

    @property
    def safe_origin(self) -> str | None:
        if self.url == "about:blank":
            return None
        return normalize_origin(self.url)

    @property
    def safe_path(self) -> str | None:
        if self.url == "about:blank":
            return None
        return _safe_path(self.url)


@runtime_checkable
class BrowserAdapter(Protocol):
    """Small synchronous boundary implemented by browser backends."""

    def connect(self) -> None: ...

    def close(self) -> None: ...

    def pages(self) -> tuple[BrowserPage, ...]: ...

    def frames(self) -> tuple[BrowserFrame, ...]: ...

    def open_page(self) -> BrowserPage: ...

    def navigate(self, url: str) -> BrowserPage: ...

    def health_check(self) -> bool: ...


class PlaywrightBrowserAdapter:
    """Optional Playwright adapter with lazy dependency and browser startup."""

    def __init__(
        self,
        *,
        browser_name: str = "chromium",
        headless: bool = True,
        cdp_endpoint: str | None = None,
        allow_existing_browser: bool = False,
        timeout_ms: int = 30_000,
    ) -> None:
        if browser_name not in {"chromium", "firefox", "webkit"}:
            raise WebStateError("browser_name must be a supported Playwright browser")
        if not isinstance(headless, bool):
            raise WebStateError("headless must be boolean")
        if not isinstance(allow_existing_browser, bool):
            raise WebStateError("allow_existing_browser must be boolean")
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or not 0 < timeout_ms <= 120_000:
            raise WebStateError("timeout_ms must be between 1 and 120000")
        if cdp_endpoint is not None:
            _bounded_text(cdp_endpoint, "cdp_endpoint", 1024)
            raise WebStateError("CDP is disabled until an isolated target contract exists")
        self._browser_name = browser_name
        self._headless = headless
        self._cdp_endpoint = cdp_endpoint
        self._allow_existing_browser = allow_existing_browser
        self._timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._context = None
        self._page_tokens: dict[int, str] = {}
        self._frame_tokens: dict[int, str] = {}
        self._next_page_token = 0
        self._next_frame_token = 0

    def _require_browser(self):
        if self._browser is None:
            raise BrowserAdapterError("adapter_not_connected")
        return self._browser

    def _page_values(self) -> tuple[BrowserPage, ...]:
        browser = self._require_browser()
        values: list[BrowserPage] = []
        contexts = (self._context,) if self._context is not None else tuple(browser.contexts)
        live_pages = [page for context in contexts for page in context.pages]
        live_ids = {id(page) for page in live_pages}
        self._page_tokens = {
            identity: token for identity, token in self._page_tokens.items() if identity in live_ids
        }
        for context in contexts:
            for page in context.pages:
                values.append(
                    BrowserPage(
                        page_id=self._stable_page_id(page),
                        frame_id="main",
                        url=page.url or "about:blank",
                    )
                )
        return tuple(values)

    def _frame_values(self) -> tuple[BrowserFrame, ...]:
        browser = self._require_browser()
        values: list[BrowserFrame] = []
        contexts = (self._context,) if self._context is not None else tuple(browser.contexts)
        live_frames = [frame for context in contexts for page in context.pages for frame in page.frames]
        live_ids = {id(frame) for frame in live_frames}
        self._frame_tokens = {
            identity: token for identity, token in self._frame_tokens.items() if identity in live_ids
        }
        for context in contexts:
            for page in context.pages:
                page_id = self._stable_page_id(page)
                for frame in page.frames:
                    values.append(
                        BrowserFrame(
                            frame_id=self._stable_frame_id(page_id, frame),
                            page_id=page_id,
                            url=frame.url or "about:blank",
                        )
                    )
        return tuple(values)

    def _stable_page_id(self, page: object) -> str:
        token = self._page_tokens.get(id(page))
        if token is None:
            token = f"page-{self._next_page_token}"
            self._next_page_token += 1
            self._page_tokens[id(page)] = token
        return token

    def _stable_frame_id(self, page_id: str, frame: object) -> str:
        token = self._frame_tokens.get(id(frame))
        if token is None:
            token = f"{page_id}-frame-{self._next_frame_token}"
            self._next_frame_token += 1
            self._frame_tokens[id(frame)] = token
        return token

    def _resolve_page_by_id(self, page_id: str):
        browser = self._require_browser()
        self._page_values()
        contexts = (self._context,) if self._context is not None else tuple(browser.contexts)
        for context in contexts:
            for page in context.pages:
                if self._stable_page_id(page) == page_id:
                    return page
        raise BrowserAdapterError("invalid_page")

    def _resolve_page(self):
        browser = self._require_browser()
        contexts = (self._context,) if self._context is not None else tuple(browser.contexts)
        pages = [page for context in contexts for page in context.pages]
        if pages:
            return pages[0]
        if self._context is not None:
            return self._context.new_page()
        if browser.contexts:
            return browser.contexts[0].new_page()
        raise BrowserAdapterError("no_page")

    def connect(self) -> None:
        if self._browser is not None:
            raise BrowserAdapterError("adapter_already_connected")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserAdapterError("adapter_unavailable") from exc
        try:
            self._playwright = sync_playwright().start()
            browser_type = getattr(self._playwright, self._browser_name)
            if self._cdp_endpoint is not None:
                self._browser = browser_type.connect_over_cdp(self._cdp_endpoint)
            else:
                self._browser = browser_type.launch(headless=self._headless)
                self._context = self._browser.new_context()
        except Exception as exc:
            self._browser = None
            self._context = None
            if self._playwright is not None:
                self._playwright.stop()
                self._playwright = None
            raise BrowserAdapterError("adapter_connect_failed") from exc

    def close(self) -> None:
        browser = self._browser
        self._browser = None
        context = self._context
        self._context = None
        try:
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()
        except Exception as exc:
            raise BrowserAdapterError("adapter_close_failed") from exc
        finally:
            if self._playwright is not None:
                self._playwright.stop()
                self._playwright = None

    def pages(self) -> tuple[BrowserPage, ...]:
        try:
            return self._page_values()
        except BrowserAdapterError:
            raise
        except Exception as exc:
            raise BrowserAdapterError("adapter_health_failed") from exc

    def frames(self) -> tuple[BrowserFrame, ...]:
        try:
            return self._frame_values()
        except BrowserAdapterError:
            raise
        except Exception as exc:
            raise BrowserAdapterError("adapter_health_failed") from exc

    def open_page(self) -> BrowserPage:
        try:
            self._resolve_page()
            return self._page_values()[0]
        except BrowserAdapterError:
            raise
        except Exception as exc:
            raise BrowserAdapterError("no_page") from exc

    def navigate(self, url: str) -> BrowserPage:
        _bounded_text(url, "url", 4096)
        try:
            page = self._resolve_page()
            page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            return self._page_values()[0]
        except BrowserAdapterError:
            raise
        except Exception as exc:
            raise BrowserAdapterError("adapter_navigation_failed") from exc

    def health_check(self) -> bool:
        try:
            browser = self._require_browser()
            return bool(browser.is_connected())
        except BrowserAdapterError:
            raise
        except Exception as exc:
            raise BrowserAdapterError("adapter_health_failed") from exc

    def extract_page_tree(
        self,
        *,
        page_id: str,
        frame_id: str,
        allowed_origins: tuple[str, ...],
        max_elements: int = 512,
    ):
        """Capture read-only DOM metadata without exposing a page handle."""

        try:
            from ..snapshots.playwright import PlaywrightDOMExtractor

            if frame_id != "main":
                raise BrowserAdapterError("invalid_page")
            page = self._resolve_page_by_id(page_id)
            observation = next(item for item in self._page_values() if item.page_id == page_id)
            if observation.safe_origin is None or observation.safe_origin not in allowed_origins:
                raise BrowserAdapterError("origin_not_allowed")
            return PlaywrightDOMExtractor(max_elements=max_elements).extract(
                page, frame_id=frame_id
            )
        except BrowserAdapterError:
            raise
        except StopIteration as exc:
            raise BrowserAdapterError("invalid_page") from exc
        except Exception as exc:
            raise BrowserAdapterError("adapter_health_failed") from exc


__all__ = [
    "BrowserAdapter",
    "BrowserAdapterError",
    "BrowserFrame",
    "BrowserPage",
    "PlaywrightBrowserAdapter",
]
