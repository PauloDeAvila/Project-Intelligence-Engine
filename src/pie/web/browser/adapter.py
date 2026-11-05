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

    def _require_browser(self):
        if self._browser is None:
            raise BrowserAdapterError("adapter_not_connected")
        return self._browser

    def _page_values(self) -> tuple[BrowserPage, ...]:
        browser = self._require_browser()
        values: list[BrowserPage] = []
        contexts = (self._context,) if self._context is not None else tuple(browser.contexts)
        for context_index, context in enumerate(contexts):
            for page_index, page in enumerate(context.pages):
                values.append(
                    BrowserPage(
                        page_id=f"context-{context_index}-page-{page_index}",
                        frame_id="main",
                        url=page.url or "about:blank",
                    )
                )
        return tuple(values)

    def _frame_values(self) -> tuple[BrowserFrame, ...]:
        browser = self._require_browser()
        values: list[BrowserFrame] = []
        contexts = (self._context,) if self._context is not None else tuple(browser.contexts)
        for context_index, context in enumerate(contexts):
            for page_index, page in enumerate(context.pages):
                page_id = f"context-{context_index}-page-{page_index}"
                for frame_index, frame in enumerate(page.frames):
                    values.append(
                        BrowserFrame(
                            frame_id=f"{page_id}-frame-{frame_index}",
                            page_id=page_id,
                            url=frame.url or "about:blank",
                        )
                    )
        return tuple(values)

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


__all__ = [
    "BrowserAdapter",
    "BrowserAdapterError",
    "BrowserFrame",
    "BrowserPage",
    "PlaywrightBrowserAdapter",
]
