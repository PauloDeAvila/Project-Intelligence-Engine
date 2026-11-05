"""Bounded, inert inputs for page-intelligence normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import unicodedata

from ..contracts import ElementSupport, WebStateError


MAX_INPUT_NODES = 2048


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise WebStateError(f"{field} must be a bounded non-empty string")
    if "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise WebStateError(f"{field} contains invalid text")
    normalized = unicodedata.normalize("NFC", value)
    return " ".join(normalized.split()) or "(unnamed)"


@dataclass(frozen=True, slots=True)
class AccessibilityNode:
    """A data-only accessibility tree node; it never carries selectors/scripts."""

    role: str
    name: str = "(unnamed)"
    children: tuple["AccessibilityNode", ...] = ()
    visible: bool = True
    enabled: bool = True
    frame_id: str = "main"
    region: str | None = None
    source: str = "accessibility_tree"

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", _text(self.role, "role", 64).casefold())
        object.__setattr__(self, "name", _text(self.name, "name", 512))
        object.__setattr__(self, "frame_id", _text(self.frame_id, "frame_id", 128))
        source = _text(self.source, "source", 64)
        if source not in {"accessibility_tree", "dom_snapshot", "semantic_snapshot"}:
            raise WebStateError("source must be a known snapshot source")
        object.__setattr__(self, "source", source)
        if self.region is not None:
            object.__setattr__(self, "region", _text(self.region, "region", 128))
        if not isinstance(self.visible, bool) or not isinstance(self.enabled, bool):
            raise WebStateError("visible and enabled must be boolean values")
        if not all(isinstance(child, AccessibilityNode) for child in self.children):
            raise WebStateError("children must contain AccessibilityNode values")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, depth: int = 0) -> "AccessibilityNode":
        """Build a node from inert data with a bounded recursive depth."""

        if not isinstance(depth, int) or isinstance(depth, bool) or not 0 <= depth <= 64:
            raise WebStateError("accessibility tree depth is outside the safe bound")
        counter = [0]

        def build(node_value: Mapping[str, Any], node_depth: int) -> AccessibilityNode:
            if node_depth > 64 or not isinstance(node_value, Mapping):
                raise WebStateError("accessibility tree exceeds safe depth or shape")
            counter[0] += 1
            if counter[0] > MAX_INPUT_NODES:
                raise WebStateError("accessibility tree exceeds the input node bound")
            children_value = node_value.get("children", ())
            if not isinstance(children_value, (tuple, list)):
                raise WebStateError("accessibility children must be a list")
            children = tuple(build(child, node_depth + 1) for child in children_value)
            return cls(
                role=node_value.get("role", "generic"),
                name=node_value.get("name", "(unnamed)"),
                children=children,
                visible=node_value.get("visible", True),
                enabled=node_value.get("enabled", True),
                frame_id=node_value.get("frame_id", "main"),
                region=node_value.get("region"),
                source=node_value.get("source", "accessibility_tree"),
            )

        if not isinstance(value, Mapping):
            raise WebStateError("accessibility tree must be a mapping")
        return build(value, depth)


@dataclass(frozen=True, slots=True)
class ElementRecord:
    """Normalized, still-untrusted element data before snapshot binding."""

    role: str
    accessible_name: str
    region: str | None
    frame_id: str
    visible: bool
    enabled: bool
    available_actions: tuple[str, ...]
    source: str
    support: ElementSupport
    unsupported_reason: str | None = None


__all__ = ["AccessibilityNode", "ElementRecord", "MAX_INPUT_NODES"]
