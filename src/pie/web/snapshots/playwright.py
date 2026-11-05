"""Read-only Playwright DOM metadata extraction for Page Intelligence."""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import MAX_PAGE_ELEMENTS, WebStateError
from .models import AccessibilityNode


_SELECTORS = (
    ("main", "main"),
    ("nav", "navigation"),
    ("form", "form"),
    ("dialog", "dialog"),
    ("button", "button"),
    ("input", "input"),
    ("textarea", "textarea"),
    ("select", "combobox"),
    ("a", "link"),
    ("h1,h2,h3,h4,h5,h6", "heading"),
    ("[role]", "generic"),
)


@dataclass(frozen=True, slots=True)
class DOMExtractionResult:
    tree: AccessibilityNode
    omitted_count: int


class PlaywrightDOMExtractor:
    """Use only fixed, read-only locators; page data remains untrusted."""

    def __init__(self, *, max_elements: int = MAX_PAGE_ELEMENTS, timeout_ms: int = 2_000) -> None:
        if not isinstance(max_elements, int) or not 1 <= max_elements <= MAX_PAGE_ELEMENTS:
            raise WebStateError("max_elements is outside the safe bound")
        if not isinstance(timeout_ms, int) or not 0 < timeout_ms <= 15_000:
            raise WebStateError("timeout_ms is outside the safe bound")
        self.max_elements = max_elements
        self.timeout_ms = timeout_ms

    def extract(self, page: object, *, title: str = "Page", frame_id: str = "main") -> DOMExtractionResult:
        if page is None or not hasattr(page, "locator"):
            raise WebStateError("page must provide a Playwright locator method")
        if frame_id != "main":
            raise WebStateError("only the main frame is supported in this phase")
        children: list[AccessibilityNode] = []
        omitted = 0
        for selector, fallback_role in _SELECTORS:
            locator = page.locator(selector)
            count = locator.count()
            for index in range(count):
                if len(children) >= self.max_elements:
                    omitted += count - index
                    break
                item = locator.nth(index)
                role = fallback_role
                name = "(unnamed)"
                for attribute in ("aria-label", "name", "placeholder", "title"):
                    try:
                        candidate = item.get_attribute(attribute, timeout=self.timeout_ms)
                    except TypeError:
                        candidate = item.get_attribute(attribute)
                    except Exception:
                        candidate = None
                    if candidate:
                        name = candidate
                        break
                if name == "(unnamed)":
                    try:
                        text = item.inner_text(timeout=self.timeout_ms)
                    except Exception:
                        text = ""
                    if text and text.strip():
                        name = text.strip()[:512]
                try:
                    explicit_role = item.get_attribute("role", timeout=self.timeout_ms)
                except TypeError:
                    explicit_role = item.get_attribute("role")
                except Exception:
                    explicit_role = None
                if explicit_role:
                    role = explicit_role
                try:
                    visible = bool(item.is_visible(timeout=self.timeout_ms))
                except Exception:
                    visible = False
                try:
                    enabled = bool(item.is_enabled(timeout=self.timeout_ms))
                except Exception:
                    enabled = False
                children.append(
                    AccessibilityNode(
                        role=role,
                        name=name,
                        visible=visible,
                        enabled=enabled,
                        frame_id=frame_id,
                        source="dom_snapshot",
                    )
                )
        return DOMExtractionResult(
            tree=AccessibilityNode(
                role="main",
                name=title or "Page",
                children=tuple(children),
                frame_id=frame_id,
                source="dom_snapshot",
            ),
            omitted_count=omitted,
        )


__all__ = ["DOMExtractionResult", "PlaywrightDOMExtractor"]
