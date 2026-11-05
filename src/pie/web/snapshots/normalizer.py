"""Turn inert page-intelligence inputs into bounded PIE snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

from ..contracts import (
    ContentTrust,
    ElementCandidate,
    ElementSupport,
    MAX_PAGE_ELEMENTS,
    PageSnapshot,
    SnapshotState,
    WebStateError,
    normalize_origin,
)
from .extractor import AccessibilityExtractor
from .models import AccessibilityNode, ElementRecord


def _safe_text(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise WebStateError(f"{field} must be a bounded non-empty string")
    if "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise WebStateError(f"{field} contains invalid text")
    return value.strip() or "(unnamed)"


def _safe_path(value: str) -> str:
    path = _safe_text(value, "path", 2048)
    if not path.startswith("/") or "?" in path or "#" in path:
        raise WebStateError("path must be path-only without query or fragment")
    return path


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    snapshot: PageSnapshot
    partial: bool


class SnapshotNormalizer:
    """Create deterministic snapshot-bound candidates from page data."""

    def __init__(self, *, extractor: AccessibilityExtractor | None = None) -> None:
        self.extractor = extractor or AccessibilityExtractor()

    def normalize(
        self,
        *,
        session_id: str,
        page_id: str,
        frame_id: str,
        generation: int,
        origin: str,
        path: str,
        title: str,
        tree: AccessibilityNode | Mapping[str, object],
        state: SnapshotState | None = None,
        captured_at: str | None = None,
    ) -> NormalizationResult:
        if isinstance(tree, Mapping):
            tree = AccessibilityNode.from_mapping(tree)
        if not isinstance(tree, AccessibilityNode):
            raise WebStateError("tree must be an AccessibilityNode or inert mapping")
        normalized_origin = normalize_origin(origin)
        normalized_path = _safe_path(path)
        normalized_title = _safe_text(title, "title", 512)
        extracted = self.extractor.extract(tree)
        effective_state = state or (SnapshotState.PARTIAL if extracted.partial else SnapshotState.CURRENT)
        if effective_state is SnapshotState.CURRENT and extracted.partial:
            raise WebStateError("CURRENT cannot be used with omitted elements")
        canonical_records = [
            {
                "role": record.role,
                "name": record.accessible_name,
                "region": record.region,
                "frame": record.frame_id,
                "visible": record.visible,
                "enabled": record.enabled,
                "actions": record.available_actions,
                "source": record.source,
                "support": record.support.value,
                "reason": record.unsupported_reason,
            }
            for record in extracted.elements
        ]
        snapshot_sha256 = _digest(
            {
                "session": session_id,
                "page": page_id,
                "frame": frame_id,
                "generation": generation,
                "origin": normalized_origin,
                "path": normalized_path,
                "title": normalized_title,
                "elements": canonical_records,
                "omitted": extracted.omitted_count,
            }
        )
        snapshot_id = f"snap-{snapshot_sha256[:24]}"
        elements = tuple(
            ElementCandidate(
                ref=f"element-{index:04d}-{_digest(canonical_records[index])[:10]}",
                session_id=session_id,
                snapshot_id=snapshot_id,
                page_id=page_id,
                generation=generation,
                snapshot_sha256=snapshot_sha256,
                role=record.role,
                accessible_name=record.accessible_name,
                region=record.region,
                frame_id=record.frame_id,
                visible=record.visible,
                enabled=record.enabled,
                available_actions=record.available_actions,
                source=record.source,
                content_trust=ContentTrust.UNTRUSTED_PAGE_DATA,
                support=record.support,
                unsupported_reason=record.unsupported_reason,
            )
            for index, record in enumerate(extracted.elements)
        )
        snapshot = PageSnapshot(
            snapshot_id=snapshot_id,
            session_id=session_id,
            page_id=page_id,
            frame_id=frame_id,
            generation=generation,
            state=effective_state,
            origin=normalized_origin,
            path=normalized_path,
            title=normalized_title,
            snapshot_sha256=snapshot_sha256,
            elements=elements,
            omitted_count=extracted.omitted_count,
            **({"captured_at": captured_at} if captured_at is not None else {}),
        )
        return NormalizationResult(snapshot, extracted.partial)


__all__ = ["NormalizationResult", "SnapshotNormalizer"]
