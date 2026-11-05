"""Session orchestration for browser adapters."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Iterable

from ..contracts import BrowserSession, SessionState, WebStateError
from .adapter import BrowserAdapter, BrowserAdapterError, BrowserFrame, BrowserPage


class BrowserConnectorError(RuntimeError):
    """Sanitized error raised by the connector boundary."""

    _CODES = frozenset(
        {
            "session_exists",
            "session_not_found",
            "session_not_ready",
            "session_closed",
            "origin_not_allowed",
            "connect_failed",
            "close_failed",
            "navigation_failed",
            "health_failed",
            "no_page",
            "invalid_page",
            "adapter_already_owned",
            "invalid_adapter",
            "page_intelligence_unavailable",
        }
    )

    def __init__(self, code: str):
        if code not in self._CODES:
            raise ValueError("unknown connector error code")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PageObservation:
    """Safe page observation with no query, fragment, credentials, or content."""

    page_id: str
    frame_id: str
    origin: str | None
    path: str | None
    generation: int


@dataclass(frozen=True, slots=True)
class FrameObservation:
    frame_id: str
    page_id: str
    origin: str | None
    path: str | None
    generation: int
    allowed: bool


@dataclass(frozen=True, slots=True)
class ConnectionResult:
    session: BrowserSession
    page: PageObservation
    pages: tuple[PageObservation, ...] = ()
    frames: tuple[FrameObservation, ...] = ()


class SessionManager:
    """Thread-safe in-memory session registry with no browser side effects."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, BrowserSession] = {}

    def create(
        self,
        *,
        session_id: str,
        adapter: str,
        allowed_origins: Iterable[str],
        capabilities: Iterable[str] = (),
    ) -> BrowserSession:
        with self._lock:
            if session_id in self._sessions:
                raise BrowserConnectorError("session_exists")
            session = BrowserSession(
                session_id=session_id,
                adapter=adapter,
                allowed_origins=tuple(allowed_origins),
                capabilities=tuple(capabilities),
            )
            self._sessions[session_id] = session
            return session

    def get(self, session_id: str) -> BrowserSession:
        with self._lock:
            try:
                return self._sessions[session_id]
            except KeyError as exc:
                raise BrowserConnectorError("session_not_found") from exc

    def update(self, session: BrowserSession) -> BrowserSession:
        with self._lock:
            if session.session_id not in self._sessions:
                raise BrowserConnectorError("session_not_found")
            self._sessions[session.session_id] = session
            return session

    def all(self) -> tuple[BrowserSession, ...]:
        with self._lock:
            return tuple(self._sessions.values())


def _observation(page: BrowserPage, generation: int) -> PageObservation:
    try:
        return PageObservation(
            page_id=page.page_id,
            frame_id=page.frame_id,
            origin=page.safe_origin,
            path=page.safe_path,
            generation=generation,
        )
    except (WebStateError, ValueError) as exc:
        raise BrowserConnectorError("invalid_page") from exc


def _frame_observation(frame: BrowserFrame, generation: int, allowed: bool) -> FrameObservation:
    try:
        return FrameObservation(
            frame_id=frame.frame_id,
            page_id=frame.page_id,
            origin=frame.safe_origin,
            path=frame.safe_path,
            generation=generation,
            allowed=allowed,
        )
    except (WebStateError, ValueError) as exc:
        raise BrowserConnectorError("invalid_page") from exc


class BrowserConnector:
    """Owns adapter lifecycle and translates it into immutable session state."""

    def __init__(self, manager: SessionManager | None = None) -> None:
        self.manager = manager or SessionManager()
        self._adapters: dict[str, BrowserAdapter] = {}
        self._adapter_owners: dict[int, str] = {}
        self._lock = RLock()

    def create_session(
        self,
        *,
        session_id: str,
        adapter: BrowserAdapter,
        adapter_name: str,
        allowed_origins: Iterable[str],
        capabilities: Iterable[str] = (),
    ) -> BrowserSession:
        with self._lock:
            if not isinstance(adapter, BrowserAdapter):
                raise BrowserConnectorError("invalid_adapter")
            adapter_identity = id(adapter)
            if adapter_identity in self._adapter_owners:
                raise BrowserConnectorError("adapter_already_owned")
            session = self.manager.create(
                session_id=session_id,
                adapter=adapter_name,
                allowed_origins=allowed_origins,
                capabilities=capabilities,
            )
            self._adapters[session_id] = adapter
            self._adapter_owners[adapter_identity] = session_id
            return session

    def session(self, session_id: str) -> BrowserSession:
        return self.manager.get(session_id)

    def _adapter(self, session_id: str) -> BrowserAdapter:
        self.manager.get(session_id)
        with self._lock:
            try:
                return self._adapters[session_id]
            except KeyError as exc:
                raise BrowserConnectorError("session_not_found") from exc

    def _inventory(
        self,
        adapter: BrowserAdapter,
        generation: int,
        allowed_origins: tuple[str, ...],
        *,
        ensure_page: bool,
    ) -> tuple[tuple[BrowserPage, ...], tuple[PageObservation, ...], tuple[FrameObservation, ...]]:
        pages = adapter.pages()
        if not pages and ensure_page:
            adapter.open_page()
            pages = adapter.pages()
        if not pages:
            raise BrowserConnectorError("no_page")
        permitted_pages: list[BrowserPage] = []
        for page in pages:
            try:
                page_origin = page.safe_origin
            except (WebStateError, ValueError) as exc:
                raise BrowserConnectorError("invalid_page") from exc
            if page_origin is None or page_origin in allowed_origins:
                permitted_pages.append(page)
        if not permitted_pages:
            raise BrowserConnectorError("origin_not_allowed")
        page_observations = tuple(_observation(page, generation) for page in permitted_pages)
        frames = adapter.frames()
        frame_observations = tuple(
            _frame_observation(
                frame,
                generation,
                frame.safe_origin is not None and frame.safe_origin in allowed_origins,
            )
            for frame in frames
        )
        return tuple(permitted_pages), page_observations, frame_observations

    def connect(self, session_id: str) -> ConnectionResult:
        with self._lock:
            return self._connect_locked(session_id)

    def _connect_locked(self, session_id: str) -> ConnectionResult:
        session = self.manager.get(session_id)
        if session.state is SessionState.CLOSED:
            raise BrowserConnectorError("session_closed")
        adapter = self._adapter(session_id)
        if session.state in {SessionState.DEGRADED, SessionState.FAILED}:
            # A recovery attempt must start from a fresh adapter observation.
            # Closing an already-lost adapter is intentionally best effort;
            # connect() remains responsible for establishing a new boundary.
            try:
                adapter.close()
            except BrowserAdapterError:
                pass
        if session.state in {SessionState.DEGRADED, SessionState.FAILED}:
            connecting = session.transition(
                SessionState.CONNECTING,
                page_id=session.current_page_id or "reconnect",
                generation=session.generation + 1,
            )
        else:
            connecting = session.transition(SessionState.CONNECTING)
        self.manager.update(connecting)
        try:
            adapter.connect()
            pages, page_observations, frame_observations = self._inventory(
                adapter,
                connecting.generation + 1,
                connecting.allowed_origins,
                ensure_page=True,
            )
            page = min(pages, key=lambda item: item.page_id)
            ready = connecting.transition(
                SessionState.READY,
                page_id=page.page_id,
                generation=connecting.generation + 1,
            )
            self.manager.update(ready)
            selected = next(item for item in page_observations if item.page_id == page.page_id)
            return ConnectionResult(ready, selected, page_observations, frame_observations)
        except BrowserConnectorError:
            failed = connecting.transition(SessionState.FAILED)
            self.manager.update(failed)
            raise
        except BrowserAdapterError as exc:
            failed = connecting.transition(SessionState.FAILED)
            self.manager.update(failed)
            code = "no_page" if exc.code == "no_page" else "connect_failed"
            raise BrowserConnectorError(code) from exc
        except Exception as exc:
            failed = connecting.transition(SessionState.FAILED)
            self.manager.update(failed)
            raise BrowserConnectorError("connect_failed") from exc

    def _record_navigation_locked(self, session_id: str, page: BrowserPage) -> ConnectionResult:
        session = self.manager.get(session_id)
        if session.state is SessionState.CLOSED:
            raise BrowserConnectorError("session_closed")
        if session.state is not SessionState.READY:
            raise BrowserConnectorError("session_not_ready")
        try:
            if page.safe_origin is not None and page.safe_origin not in session.allowed_origins:
                raise BrowserConnectorError("origin_not_allowed")
        except BrowserConnectorError:
            raise
        except Exception as exc:
            raise BrowserConnectorError("invalid_page") from exc
        ready = session.transition(
            SessionState.READY,
            page_id=page.page_id,
            generation=session.generation + 1,
        )
        self.manager.update(ready)
        adapter = self._adapter(session_id)
        try:
            pages, page_observations, frame_observations = self._inventory(
                adapter,
                ready.generation,
                ready.allowed_origins,
                ensure_page=False,
            )
        except BrowserAdapterError as exc:
            self.mark_degraded(session_id)
            raise BrowserConnectorError("navigation_failed") from exc
        except BrowserConnectorError:
            self.mark_degraded(session_id)
            raise
        except Exception as exc:
            self.mark_degraded(session_id)
            raise BrowserConnectorError("navigation_failed") from exc
        selected = next((item for item in page_observations if item.page_id == page.page_id), None)
        if selected is None:
            self._mark_degraded_locked(session_id)
            raise BrowserConnectorError("invalid_page")
        return ConnectionResult(ready, selected, page_observations, frame_observations)

    def navigate(self, session_id: str, url: str) -> ConnectionResult:
        with self._lock:
            session = self.manager.get(session_id)
            if session.state is not SessionState.READY:
                raise BrowserConnectorError("session_not_ready")
            try:
                allowed = session.allows(url)
            except Exception as exc:
                raise BrowserConnectorError("origin_not_allowed") from exc
            if not allowed:
                raise BrowserConnectorError("origin_not_allowed")
            adapter = self._adapter(session_id)
            try:
                page = adapter.navigate(url)
            except BrowserAdapterError as exc:
                raise BrowserConnectorError("navigation_failed") from exc
            try:
                final_origin = page.safe_origin
                if final_origin is None or final_origin not in session.allowed_origins:
                    self.mark_degraded(session_id)
                    raise BrowserConnectorError("origin_not_allowed")
            except BrowserConnectorError:
                raise
            except Exception as exc:
                self.mark_degraded(session_id)
                raise BrowserConnectorError("origin_not_allowed") from exc
            return self._record_navigation_locked(session_id, page)

    def close(self, session_id: str) -> BrowserSession:
        with self._lock:
            return self._close_locked(session_id)

    def _close_locked(self, session_id: str) -> BrowserSession:
        session = self.manager.get(session_id)
        if session.state is SessionState.CLOSED:
            return session
        adapter = self._adapter(session_id)
        error: BrowserConnectorError | None = None
        try:
            adapter.close()
        except BrowserAdapterError as exc:
            error = BrowserConnectorError("close_failed")
            error.__cause__ = exc
        closed = session.transition(SessionState.CLOSED)
        self.manager.update(closed)
        if error is not None:
            raise error
        return closed

    def mark_degraded(self, session_id: str) -> BrowserSession:
        with self._lock:
            return self._mark_degraded_locked(session_id)

    def _mark_degraded_locked(self, session_id: str) -> BrowserSession:
        session = self.manager.get(session_id)
        if session.state is SessionState.CLOSED:
            return session
        if session.state is SessionState.READY:
            session = session.transition(SessionState.DEGRADED)
            self.manager.update(session)
        return session

    def health_check(self, session_id: str) -> tuple[bool, BrowserSession]:
        with self._lock:
            session = self.manager.get(session_id)
            if session.state is SessionState.CLOSED:
                return False, session
            adapter = self._adapter(session_id)
            try:
                healthy = bool(adapter.health_check())
            except BrowserAdapterError:
                healthy = False
            if healthy:
                return True, session
            return False, self._mark_degraded_locked(session_id)

    def extract_page_tree(
        self,
        session_id: str,
        *,
        page_id: str | None = None,
        frame_id: str = "main",
        max_elements: int = 512,
    ):
        """Extract bounded page metadata only through an authorized session."""

        with self._lock:
            session = self.manager.get(session_id)
            if session.state is not SessionState.READY:
                raise BrowserConnectorError("session_not_ready")
            adapter = self._adapter(session_id)
            try:
                pages, observations, frames = self._inventory(
                    adapter,
                    session.generation,
                    session.allowed_origins,
                    ensure_page=False,
                )
            except BrowserConnectorError:
                raise
            target_id = page_id or session.current_page_id
            if target_id is None or not any(item.page_id == target_id for item in pages):
                raise BrowserConnectorError("invalid_page")
            if frame_id == "main":
                target_frame_allowed = any(
                    item.page_id == target_id and item.origin in session.allowed_origins
                    for item in observations
                )
            else:
                target_frame = next(
                    (item for item in frames if item.page_id == target_id and item.frame_id == frame_id),
                    None,
                )
                target_frame_allowed = target_frame is not None and target_frame.allowed
            if not target_frame_allowed:
                raise BrowserConnectorError("origin_not_allowed")
            extractor = getattr(adapter, "extract_page_tree", None)
            if not callable(extractor):
                raise BrowserConnectorError("page_intelligence_unavailable")
            try:
                return extractor(
                    page_id=target_id,
                    frame_id=frame_id,
                    allowed_origins=session.allowed_origins,
                    max_elements=max_elements,
                )
            except BrowserAdapterError as exc:
                if exc.code == "origin_not_allowed":
                    raise BrowserConnectorError("origin_not_allowed") from exc
                raise BrowserConnectorError("invalid_page") from exc


__all__ = [
    "BrowserConnector",
    "BrowserConnectorError",
    "ConnectionResult",
    "FrameObservation",
    "PageObservation",
    "SessionManager",
]
