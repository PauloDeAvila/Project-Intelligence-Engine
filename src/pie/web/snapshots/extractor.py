"""Accessibility extraction without selectors, scripts, or model calls."""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import ElementSupport, MAX_PAGE_ELEMENTS, WebStateError
from .models import AccessibilityNode, ElementRecord


_ROLE_MAP = {
    "textbox": "input",
    "searchbox": "input",
    "textarea": "textarea",
    "select": "combobox",
    "menu": "menu",
    "menuitem": "menuitem",
    "table": "table",
    "grid": "grid",
    "row": "row",
    "cell": "cell",
    "tab": "tab",
    "tabpanel": "tabpanel",
    "list": "list",
    "listitem": "listitem",
    "tree": "tree",
    "treeitem": "treeitem",
}
_SUPPORTED_ROLES = frozenset(
    {"button", "checkbox", "combobox", "dialog", "form", "heading", "input", "link", "main", "navigation", "textarea"}
)
_KNOWN_ROLES = _SUPPORTED_ROLES | frozenset(_ROLE_MAP) | {"image", "generic", "text"}


def _actions_for(role: str, enabled: bool, supported: bool) -> tuple[str, ...]:
    if not enabled or not supported:
        return ()
    return {
        "button": ("click",),
        "checkbox": ("click",),
        "combobox": ("select",),
        "input": ("type",),
        "textarea": ("type",),
        "link": ("open",),
    }.get(role, ())


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    elements: tuple[ElementRecord, ...]
    omitted_count: int
    partial: bool


class AccessibilityExtractor:
    """Flatten a bounded tree while preserving unsupported nodes explicitly."""

    def __init__(
        self,
        *,
        max_elements: int = MAX_PAGE_ELEMENTS,
        max_depth: int = 64,
        max_input_nodes: int = 2048,
    ) -> None:
        if not isinstance(max_elements, int) or not 1 <= max_elements <= MAX_PAGE_ELEMENTS:
            raise WebStateError("max_elements is outside the safe bound")
        if not isinstance(max_depth, int) or not 1 <= max_depth <= 128:
            raise WebStateError("max_depth is outside the safe bound")
        if not isinstance(max_input_nodes, int) or not 1 <= max_input_nodes <= 4096:
            raise WebStateError("max_input_nodes is outside the safe bound")
        self.max_elements = max_elements
        self.max_depth = max_depth
        self.max_input_nodes = max_input_nodes

    def extract(self, root: AccessibilityNode) -> ExtractionResult:
        if not isinstance(root, AccessibilityNode):
            raise WebStateError("root must be an AccessibilityNode")
        records: list[ElementRecord] = []
        omitted = 0
        partial = False
        visited = 0
        budget_exhausted = False

        def visit(node: AccessibilityNode, depth: int, inherited_region: str | None) -> None:
            nonlocal omitted, partial, visited, budget_exhausted
            if budget_exhausted:
                return
            if depth > self.max_depth:
                omitted += 1
                partial = True
                return
            visited += 1
            if visited > self.max_input_nodes:
                omitted += 1
                partial = True
                budget_exhausted = True
                return
            if len(records) >= self.max_elements:
                omitted += 1
                partial = True
                budget_exhausted = True
                return
            mapped_role = _ROLE_MAP.get(node.role, node.role if node.role in _KNOWN_ROLES else "generic")
            supported = mapped_role in _SUPPORTED_ROLES
            reason = None if supported else "unsupported_role"
            region = node.region or inherited_region
            records.append(
                ElementRecord(
                    role=mapped_role,
                    accessible_name=node.name,
                    region=region,
                    frame_id=node.frame_id,
                    visible=node.visible,
                    enabled=node.enabled,
                    available_actions=_actions_for(mapped_role, node.enabled, supported),
                    source=node.source,
                    support=ElementSupport.SUPPORTED if supported else ElementSupport.UNSUPPORTED,
                    unsupported_reason=reason,
                )
            )
            next_region = node.name if node.role in {"main", "navigation", "form", "dialog"} else region
            for child_index, child in enumerate(node.children):
                if budget_exhausted:
                    omitted += len(node.children) - child_index
                    partial = True
                    return
                visit(child, depth + 1, next_region)
                if budget_exhausted:
                    omitted += len(node.children) - child_index - 1
                    partial = True
                    return

        visit(root, 0, None)
        return ExtractionResult(tuple(records), omitted, partial)


__all__ = ["AccessibilityExtractor", "ExtractionResult"]
