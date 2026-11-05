"""Dependency-free contracts for PIE Web Intelligence phase 0.

The module describes state and evidence only. It does not start browsers,
make network requests, execute JavaScript, or authorize an action.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import json
import math
import re
from typing import Any, Mapping
from urllib.parse import SplitResult, urlsplit


WEB_CONTRACT_SCHEMA = "pie-web-contracts-v1"
_SENSITIVE_KEY_NAMES = {
    "password",
    "token",
    "api_key",
    "authorization",
    "cookie",
    "secret",
}
_SENSITIVE_TEXT = re.compile(
    r"(?i)[\"']?(password|token|api[_ -]?key|authorization|bearer|cookie|secret)[\"']?\s*[:=]\s*(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\S+)"
)
_AUTH_TEXT = re.compile(r"(?i)\bauthorization\s*:\s*(?:bearer|basic)\s+\S+")
_BEARER_TEXT = re.compile(r"(?i)\b(?:bearer|basic)\s+\S+")
_SAFE_ERROR_CODES = {
    "action_blocked",
    "action_rejected",
    "execution_failed",
    "origin_not_allowed",
    "session_failed",
    "stale_reference",
    "timeout",
    "verification_failed",
}
_SAFE_ACTIONS = {
    "back",
    "click",
    "forward",
    "hover",
    "navigate",
    "open",
    "scroll",
    "select",
    "submit",
    "type",
    "wait",
}
_SAFE_METRIC_OPERATIONS = {
    "execute_action",
    "find_candidates",
    "plan_action",
    "session",
    "snapshot",
}
_SAFE_METRIC_STATUSES = {"blocked", "failed", "ok", "partial", "stale", "timeout"}
_MAX_SAFE_INTEGER = 10**12
_SAFE_ROLES = {
    "button",
    "checkbox",
    "combobox",
    "dialog",
    "form",
    "generic",
    "heading",
    "image",
    "input",
    "link",
    "main",
    "navigation",
    "text",
}
_SAFE_SOURCES = {"accessibility_tree", "semantic_snapshot"}


class WebStateError(ValueError):
    """Raised when a web contract contains invalid or unsafe state."""


class SessionState(str, Enum):
    NEW = "NEW"
    CONNECTING = "CONNECTING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    CLOSED = "CLOSED"


class SnapshotState(str, Enum):
    CURRENT = "CURRENT"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    BLOCKED = "BLOCKED"


class ReferenceState(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ContentTrust(str, Enum):
    UNTRUSTED_PAGE_DATA = "UNTRUSTED_PAGE_DATA"


class ActionStatus(str, Enum):
    PLANNED = "PLANNED"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    STALE = "STALE"


class ExecutionState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    UNKNOWN = "UNKNOWN"


class VerificationState(str, Enum):
    NOT_RUN = "NOT_RUN"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class _Contract:
    """Common deterministic serialization for all phase-0 contracts."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": WEB_CONTRACT_SCHEMA,
            "value": _redact_jsonable(_jsonable(asdict(self))),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _redact_jsonable(value: Any, key: str | None = None) -> Any:
    if key and key.casefold() in _SENSITIVE_KEY_NAMES:
        return "[REDACTED]"
    if key == "error_code" and isinstance(value, str) and value not in _SAFE_ERROR_CODES:
        return "[REDACTED]"
    if key in {"title", "accessible_name", "region", "goal", "target_query"} and isinstance(value, str):
        return "[REDACTED_PAGE_DATA]"
    if key == "path" and isinstance(value, str):
        parts = value.split("/")
        safe_parts = [
            "[REDACTED]" if part else ""
            for part in parts
        ]
        return "/".join(safe_parts)
    if isinstance(value, Mapping):
        return {
            str(item_key): _redact_jsonable(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_jsonable(item) for item in value]
    if isinstance(value, str):
        value = _AUTH_TEXT.sub("Authorization: [REDACTED]", value)
        value = _BEARER_TEXT.sub("[REDACTED]", value)
        return _SENSITIVE_TEXT.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp(value: object, field_name: str) -> str:
    value = _text(value, field_name, maximum=128)
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-](?:0\d|1\d|2[0-3]):[0-5]\d)",
        value,
    ):
        raise WebStateError(f"{field_name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise WebStateError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise WebStateError(f"{field_name} must include a timezone")
    return value


def _text(value: object, field_name: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise WebStateError(f"{field_name} must be a string")
    value = value.strip()
    if not value:
        raise WebStateError(f"{field_name} must not be empty")
    if "\x00" in value:
        raise WebStateError(f"{field_name} must not contain NUL")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise WebStateError(f"{field_name} must not contain isolated Unicode surrogates")
    if len(value) > maximum:
        raise WebStateError(f"{field_name} exceeds {maximum} characters")
    return value


def _nonnegative(value: object, field_name: str, *, integer: bool = False) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WebStateError(f"{field_name} must be a non-negative number")
    if integer and not isinstance(value, int):
        raise WebStateError(f"{field_name} must be a non-negative integer")
    if isinstance(value, int):
        if value < 0 or value > _MAX_SAFE_INTEGER:
            raise WebStateError(f"{field_name} must be a non-negative number")
        return value
    if not math.isfinite(value) or value < 0:
        raise WebStateError(f"{field_name} must be a non-negative number")
    return value


def _parts(url: str) -> SplitResult:
    url = _text(url, "url", maximum=4096)
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise WebStateError("url contains an invalid authority") from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise WebStateError("url must be an absolute http(s) URL")
    if "*" in parts.hostname:
        raise WebStateError("wildcard origins are not supported")
    if "@" in parts.netloc or parts.username or parts.password:
        raise WebStateError("url must not contain credentials")
    if parts.netloc.startswith("[") and ":" not in parts.hostname:
        raise WebStateError("bracketed hosts must be valid IPv6 addresses")
    try:
        parts.port
    except ValueError as exc:
        raise WebStateError("url contains an invalid port") from exc
    return parts


def normalize_origin(url: str) -> str:
    """Return a canonical, credential-free origin for an absolute URL."""

    parts = _parts(url)
    hostname = parts.hostname.lower()
    if not hostname:
        raise WebStateError("url contains an empty host")
    if any(character.isspace() for character in hostname) or "%" in hostname:
        raise WebStateError("url contains an invalid or encoded host")
    if ":" in hostname:
        import ipaddress

        try:
            hostname = ipaddress.IPv6Address(hostname).compressed.lower()
        except ValueError as exc:
            raise WebStateError("url contains an invalid IPv6 host") from exc
        hostname = f"[{hostname}]"
    else:
        if not re.fullmatch(r"[A-Za-z0-9.-]+", hostname):
            raise WebStateError("url contains an invalid host")
        labels = hostname.split(".")
        if any(
            not label
            or len(label) > 63
            or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
            for label in labels
        ):
            raise WebStateError("url contains an invalid DNS hostname")
        last_label = labels[-1]
        numeric_last_label = re.fullmatch(r"\d+", last_label) or re.fullmatch(
            r"0[xX][0-9A-Fa-f]*", last_label
        )
        if numeric_last_label and not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", hostname):
            raise WebStateError("legacy numeric IPv4 forms are not supported")
        if re.fullmatch(r"\d+(?:\.\d+){3}", hostname):
            import ipaddress

            try:
                hostname = str(ipaddress.IPv4Address(hostname))
            except ValueError as exc:
                raise WebStateError("url contains an invalid IPv4 host") from exc
    port = parts.port
    default_port = (parts.scheme == "http" and port == 80) or (
        parts.scheme == "https" and port == 443
    )
    suffix = "" if port is None or default_port else f":{port}"
    return f"{parts.scheme}://{hostname}{suffix}"


def _origin_policy(value: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for origin in value:
        parts = _parts(origin)
        if parts.path not in {"", "/"} or parts.query or parts.fragment:
            raise WebStateError("allowed origins must not contain a path or query")
        canonical = normalize_origin(origin)
        if canonical not in normalized:
            normalized.append(canonical)
    return tuple(normalized)


def _unsafe_intent_text(value: str, field_name: str) -> None:
    lowered = value.casefold()
    patterns = (
        r"javascript\s*:",
        r"\bdata\s*:",
        r"\bfile\s*:",
        r"document\s*\.\s*queryselector",
        r"\b(?:document|window)\s*\.\s*[a-z_][a-z0-9_]*",
        r"\b(?:getelementbyid|eval)\s*\(",
        r"\b(?:alert|location)\s*\.?\s*[a-z_]*\s*\(",
        r"\b(?:css|xpath)\s*(?:selector|=|:)",
        r"(?:^|\s)#[-_a-z0-9]+",
        r"(?:^|\s)\.?//",
        r"\[@[a-z0-9_-]+\s*=",
        r"\bqueryselector\b",
        r"\b(?:x|y)\s*=\s*\d",
        r"\b(?:cookie|authorization|bearer|api[_ -]?key|password|secret|token)\b",
        r"\bcoordinates?\b",
        r"\b\d{1,5}\s*,\s*\d{1,5}\b",
    )
    if any(re.search(pattern, lowered) for pattern in patterns):
        raise WebStateError(
            f"{field_name} contains an executable selector or sensitive value"
        )


@dataclass(frozen=True, slots=True)
class BrowserSession(_Contract):
    """Serializable session state; it is not a live browser connection."""

    session_id: str
    adapter: str
    state: SessionState = SessionState.NEW
    allowed_origins: tuple[str, ...] = ()
    current_page_id: str | None = None
    generation: int = 0
    capabilities: tuple[str, ...] = ()
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _text(self.session_id, "session_id", maximum=128))
        object.__setattr__(self, "adapter", _text(self.adapter, "adapter", maximum=64))
        if not isinstance(self.state, SessionState):
            raise WebStateError("state must be a SessionState")
        if self.state == SessionState.READY and self.current_page_id is None:
            raise WebStateError("a ready session needs a page_id")
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        object.__setattr__(self, "allowed_origins", _origin_policy(tuple(self.allowed_origins)))
        if self.current_page_id is not None:
            object.__setattr__(
                self,
                "current_page_id",
                _text(self.current_page_id, "current_page_id", maximum=128),
            )
        _nonnegative(self.generation, "generation", integer=True)
        capabilities = tuple(_text(item, "capability", maximum=64) for item in self.capabilities)
        object.__setattr__(self, "capabilities", tuple(dict.fromkeys(capabilities)))

    def allows(self, url: str) -> bool:
        """Check an exact origin allowlist; wildcard matching is unsupported."""

        return normalize_origin(url) in self.allowed_origins

    def transition(
        self,
        state: SessionState,
        *,
        page_id: str | None = None,
        generation: int | None = None,
    ) -> "BrowserSession":
        if not isinstance(state, SessionState):
            raise WebStateError("state must be a SessionState")
        normalized_page_id = (
            None
            if page_id is None
            else _text(page_id, "page_id", maximum=128)
        )
        normalized_generation = (
            None
            if generation is None
            else _nonnegative(generation, "generation", integer=True)
        )
        allowed = {
            SessionState.NEW: {SessionState.CONNECTING, SessionState.CLOSED},
            SessionState.CONNECTING: {
                SessionState.READY,
                SessionState.DEGRADED,
                SessionState.FAILED,
                SessionState.CLOSED,
            },
            SessionState.READY: {
                SessionState.DEGRADED,
                SessionState.FAILED,
                SessionState.CLOSED,
            },
            SessionState.DEGRADED: {
                SessionState.CONNECTING,
                SessionState.READY,
                SessionState.FAILED,
                SessionState.CLOSED,
            },
            SessionState.FAILED: {SessionState.CONNECTING, SessionState.CLOSED},
            SessionState.CLOSED: set(),
        }
        if state not in allowed[self.state]:
            raise WebStateError(f"invalid session transition: {self.state.value} -> {state.value}")
        if state == SessionState.READY and normalized_page_id is None and self.current_page_id is None:
            raise WebStateError("a ready session needs a page_id")
        if self.state in {SessionState.FAILED, SessionState.DEGRADED} and state in {
            SessionState.CONNECTING,
            SessionState.READY,
        }:
            if (
                normalized_page_id is None
                or normalized_generation is None
                or normalized_generation <= self.generation
            ):
                raise WebStateError("reconnecting needs a new page and generation")
        if self.state == SessionState.CONNECTING and state == SessionState.READY:
            if (
                normalized_page_id is None
                or normalized_generation is None
                or normalized_generation <= self.generation
            ):
                raise WebStateError("ready state needs a fresh page observation")
        next_generation = self.generation if normalized_generation is None else normalized_generation
        if next_generation < self.generation:
            raise WebStateError("session generation cannot move backwards")
        return replace(
            self,
            state=state,
            current_page_id=normalized_page_id if normalized_page_id is not None else self.current_page_id,
            generation=next_generation,
        )


@dataclass(frozen=True, slots=True)
class ElementReference(_Contract):
    """A snapshot-bound handle; it is never valid without its snapshot id."""

    ref: str
    session_id: str
    page_id: str
    frame_id: str
    snapshot_id: str
    snapshot_sha256: str
    generation: int
    state: ReferenceState = ReferenceState.CURRENT

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref", _text(self.ref, "ref", maximum=128))
        object.__setattr__(self, "session_id", _text(self.session_id, "session_id", maximum=128))
        object.__setattr__(self, "page_id", _text(self.page_id, "page_id", maximum=128))
        object.__setattr__(self, "frame_id", _text(self.frame_id, "frame_id", maximum=128))
        object.__setattr__(self, "snapshot_id", _text(self.snapshot_id, "snapshot_id", maximum=128))
        snapshot_sha256 = _text(self.snapshot_sha256, "snapshot_sha256", maximum=64).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256):
            raise WebStateError("snapshot_sha256 must be a 64-character lowercase hex digest")
        object.__setattr__(self, "snapshot_sha256", snapshot_sha256)
        _nonnegative(self.generation, "generation", integer=True)
        if not isinstance(self.state, ReferenceState):
            raise WebStateError("state must be a ReferenceState")


@dataclass(frozen=True, slots=True)
class ElementCandidate(_Contract):
    """An actionable or informational element extracted from a page."""

    ref: str
    session_id: str
    snapshot_id: str
    page_id: str
    generation: int
    snapshot_sha256: str
    role: str
    accessible_name: str
    region: str | None = None
    frame_id: str = "main"
    visible: bool = True
    enabled: bool = True
    available_actions: tuple[str, ...] = ()
    source: str = "accessibility_tree"
    content_trust: ContentTrust = ContentTrust.UNTRUSTED_PAGE_DATA
    reference_state: ReferenceState = ReferenceState.CURRENT

    @property
    def reference(self) -> ElementReference:
        return ElementReference(
            self.ref,
            self.session_id,
            self.page_id,
            self.frame_id,
            self.snapshot_id,
            self.snapshot_sha256,
            self.generation,
            self.reference_state,
        )

    def __post_init__(self) -> None:
        for field_name in ("ref", "session_id", "snapshot_id", "page_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name, maximum=128))
        _nonnegative(self.generation, "generation", integer=True)
        snapshot_sha256 = _text(self.snapshot_sha256, "snapshot_sha256", maximum=64).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256):
            raise WebStateError("snapshot_sha256 must be a 64-character lowercase hex digest")
        object.__setattr__(self, "snapshot_sha256", snapshot_sha256)
        role = _text(self.role, "role", maximum=64).casefold()
        if role not in _SAFE_ROLES:
            raise WebStateError("role must be a known semantic role")
        object.__setattr__(self, "role", role)
        object.__setattr__(
            self,
            "accessible_name",
            _text(self.accessible_name, "accessible_name", maximum=512),
        )
        object.__setattr__(self, "frame_id", _text(self.frame_id, "frame_id", maximum=128))
        source = _text(self.source, "source", maximum=64)
        if source not in _SAFE_SOURCES:
            raise WebStateError("source must be a known semantic source")
        object.__setattr__(self, "source", source)
        if self.content_trust is not ContentTrust.UNTRUSTED_PAGE_DATA:
            raise WebStateError("page-derived elements must remain untrusted")
        if not isinstance(self.reference_state, ReferenceState):
            raise WebStateError("reference_state must be a ReferenceState")
        if self.region is not None:
            object.__setattr__(self, "region", _text(self.region, "region", maximum=128))
        if not isinstance(self.visible, bool) or not isinstance(self.enabled, bool):
            raise WebStateError("visible and enabled must be boolean values")
        cleaned = tuple(_text(action, "action", maximum=64).casefold() for action in self.available_actions)
        if any(action not in _SAFE_ACTIONS for action in cleaned):
            raise WebStateError("available_actions must contain known declarative operations")
        object.__setattr__(self, "available_actions", tuple(dict.fromkeys(cleaned)))


@dataclass(frozen=True, slots=True)
class PageSnapshot(_Contract):
    """A bounded, immutable page observation with snapshot-bound candidates."""

    snapshot_id: str
    session_id: str
    page_id: str
    frame_id: str
    generation: int
    state: SnapshotState
    origin: str
    path: str
    title: str
    snapshot_sha256: str
    elements: tuple[ElementCandidate, ...] = ()
    omitted_count: int = 0
    captured_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        for field_name in ("snapshot_id", "session_id", "page_id", "frame_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name, maximum=128))
        _nonnegative(self.generation, "generation", integer=True)
        if not isinstance(self.state, SnapshotState):
            raise WebStateError("state must be a SnapshotState")
        object.__setattr__(self, "origin", normalize_origin(self.origin))
        path = _text(self.path, "path", maximum=2048)
        if not path.startswith("/") or "?" in path or "#" in path:
            raise WebStateError("path must be a path-only value without query or fragment")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "title", _text(self.title, "title", maximum=512))
        object.__setattr__(self, "captured_at", _timestamp(self.captured_at, "captured_at"))
        snapshot_sha256 = _text(self.snapshot_sha256, "snapshot_sha256", maximum=64).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256):
            raise WebStateError("snapshot_sha256 must be a 64-character lowercase hex digest")
        object.__setattr__(self, "snapshot_sha256", snapshot_sha256)
        _nonnegative(self.omitted_count, "omitted_count", integer=True)
        elements = tuple(self.elements)
        refs: set[str] = set()
        reference_state = (
            ReferenceState.CURRENT
            if self.state == SnapshotState.CURRENT
            else ReferenceState.STALE
            if self.state == SnapshotState.STALE
            else ReferenceState.UNKNOWN
        )
        normalized_elements: list[ElementCandidate] = []
        for element in elements:
            if not isinstance(element, ElementCandidate):
                raise WebStateError("elements must contain ElementCandidate values")
            if element.ref in refs:
                raise WebStateError("element refs must be unique within a snapshot")
            refs.add(element.ref)
            if element.reference_state is not ReferenceState.CURRENT:
                raise WebStateError("snapshot candidates must start as current references")
            if (
                element.session_id != self.session_id
                or element.page_id != self.page_id
                or element.frame_id != self.frame_id
                or element.snapshot_id != self.snapshot_id
                or element.generation != self.generation
                or element.snapshot_sha256 != self.snapshot_sha256
            ):
                raise WebStateError("element does not belong to this snapshot")
            normalized_elements.append(replace(element, reference_state=reference_state))
        object.__setattr__(self, "elements", tuple(normalized_elements))

    def find(self, ref: str) -> ElementCandidate | None:
        return next((element for element in self.elements if element.ref == ref), None)


@dataclass(frozen=True, slots=True)
class TaskIntent(_Contract):
    """A model-level objective; it contains no executable selector or script."""

    intent_id: str
    session_id: str
    page_id: str | None
    goal: str
    action: str | None = None
    target_query: str | None = None
    expected_transition: str | None = None
    max_candidates: int = 10
    context_budget_chars: int = 12000

    def __post_init__(self) -> None:
        for field_name in ("intent_id", "session_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name, maximum=128))
        if self.page_id is not None:
            object.__setattr__(self, "page_id", _text(self.page_id, "page_id", maximum=128))
        object.__setattr__(self, "goal", _text(self.goal, "goal", maximum=4000))
        for field_name in ("action", "target_query", "expected_transition"):
            value = getattr(self, field_name)
            if value is not None:
                value = _text(value, field_name, maximum=1024)
                if field_name == "action":
                    _unsafe_intent_text(value, field_name)
                if field_name == "expected_transition" and not re.fullmatch(
                    r"[A-Za-z][A-Za-z0-9_.-]{0,127}", value
                ):
                    raise WebStateError("expected_transition must be a symbolic state name")
                object.__setattr__(self, field_name, value)
        if self.action is not None:
            action = self.action.casefold()
            if action not in _SAFE_ACTIONS:
                raise WebStateError("action must be a declarative web operation")
            object.__setattr__(self, "action", action)
        _nonnegative(self.max_candidates, "max_candidates", integer=True)
        _nonnegative(self.context_budget_chars, "context_budget_chars", integer=True)
        if self.max_candidates == 0 or self.context_budget_chars == 0:
            raise WebStateError("intent budgets must be greater than zero")


@dataclass(frozen=True, slots=True)
class ActionResult(_Contract):
    """Outcome envelope; execution remains outside this phase-0 module."""

    action_id: str
    intent_id: str
    status: ActionStatus
    execution_state: ExecutionState
    verification: VerificationState
    session_id: str
    page_id: str
    snapshot_before: str
    snapshot_after: str | None = None
    target_ref: str | None = None
    latency_ms: float = 0.0
    error_code: str | None = None
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "action_id",
            "intent_id",
            "session_id",
            "page_id",
            "snapshot_before",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name, maximum=128))
        for field_name in ("snapshot_after", "target_ref", "error_code"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _text(value, field_name, maximum=128))
        if not isinstance(self.status, ActionStatus):
            raise WebStateError("status must be an ActionStatus")
        if not isinstance(self.execution_state, ExecutionState):
            raise WebStateError("execution_state must be an ExecutionState")
        if not isinstance(self.verification, VerificationState):
            raise WebStateError("verification must be a VerificationState")
        object.__setattr__(self, "latency_ms", _nonnegative(self.latency_ms, "latency_ms"))
        object.__setattr__(
            self,
            "evidence_ids",
            tuple(_text(value, "evidence_id", maximum=128) for value in self.evidence_ids),
        )
        if self.status == ActionStatus.SUCCEEDED and (
            self.execution_state != ExecutionState.COMPLETED
            or self.verification != VerificationState.VERIFIED
            or self.error_code is not None
        ):
            raise WebStateError("SUCCEEDED requires completed execution and positive verification")
        if self.status == ActionStatus.PLANNED and (
            self.execution_state != ExecutionState.NOT_STARTED
            or self.verification != VerificationState.NOT_RUN
            or self.error_code is not None
        ):
            raise WebStateError("PLANNED requires not-started execution without an error")
        expected_error_codes = {
            ActionStatus.BLOCKED: "action_blocked",
            ActionStatus.REJECTED: "action_rejected",
            ActionStatus.STALE: "stale_reference",
            ActionStatus.TIMEOUT: "timeout",
        }
        expected_error_code = expected_error_codes.get(self.status)
        if expected_error_code is not None and self.error_code != expected_error_code:
            raise WebStateError(f"{self.status.value} requires error_code={expected_error_code}")
        if self.status == ActionStatus.TIMEOUT and (
            self.execution_state != ExecutionState.UNKNOWN
            or self.verification != VerificationState.NOT_RUN
        ):
            raise WebStateError("TIMEOUT requires unknown execution without verification")
        if self.status in {
            ActionStatus.BLOCKED,
            ActionStatus.REJECTED,
            ActionStatus.STALE,
        } and (
            self.execution_state != ExecutionState.NOT_STARTED
            or self.verification != VerificationState.NOT_RUN
        ):
            raise WebStateError("blocked, rejected, and stale actions cannot execute or verify")
        if self.status == ActionStatus.FAILED:
            execution_failure = (
                self.error_code == "execution_failed"
                and self.execution_state in {ExecutionState.STARTED, ExecutionState.UNKNOWN}
                and self.verification == VerificationState.NOT_RUN
            )
            verification_failure = (
                self.error_code == "verification_failed"
                and self.execution_state == ExecutionState.COMPLETED
                and self.verification == VerificationState.FAILED
            )
            if not (execution_failure or verification_failure):
                raise WebStateError("FAILED must distinguish execution and verification failure")


@dataclass(frozen=True, slots=True)
class WebMetric(_Contract):
    """Bounded operational telemetry that excludes page content and secrets."""

    operation: str
    status: str
    duration_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation", _text(self.operation, "operation", maximum=128))
        object.__setattr__(self, "status", _text(self.status, "status", maximum=64))
        if self.operation not in _SAFE_METRIC_OPERATIONS:
            raise WebStateError("operation must be a known telemetry operation")
        if self.status not in _SAFE_METRIC_STATUSES:
            raise WebStateError("status must be a known telemetry status")
        object.__setattr__(self, "duration_ms", _nonnegative(self.duration_ms, "duration_ms"))
        for field_name in ("input_tokens", "output_tokens"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _nonnegative(value, field_name, integer=True))
        if self.error_code is not None:
            error_code = _text(self.error_code, "error_code", maximum=128)
            if error_code not in _SAFE_ERROR_CODES:
                raise WebStateError("error_code must be a known operational code")
            object.__setattr__(self, "error_code", error_code)
