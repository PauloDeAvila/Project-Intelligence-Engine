"""Deterministic token extraction from snapshot-bound candidates."""

from __future__ import annotations

from dataclasses import replace
import re
import unicodedata

from ..contracts import ElementCandidate, PageSnapshot, WebStateError
from .models import SearchDocument


_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
_MAX_QUERY_TOKENS = 32


def tokenize(value: str, *, maximum: int = _MAX_QUERY_TOKENS) -> tuple[str, ...]:
    if not isinstance(value, str) or len(value) > 512:
        raise WebStateError("search text is outside the safe bound")
    normalized = unicodedata.normalize("NFC", value).casefold()
    tokens = tuple(dict.fromkeys(match.group(0) for match in _TOKEN_RE.finditer(normalized)))
    if len(tokens) > maximum:
        raise WebStateError("search text contains too many terms")
    return tokens


class CandidateExtractor:
    """Build a bounded in-memory search document for each page candidate."""

    def __init__(self, *, max_candidates: int = 512) -> None:
        if not isinstance(max_candidates, int) or isinstance(max_candidates, bool) or not 1 <= max_candidates <= 512:
            raise WebStateError("max_candidates is outside the safe bound")
        self.max_candidates = max_candidates

    def extract(self, snapshot: PageSnapshot) -> tuple[SearchDocument, ...]:
        if not isinstance(snapshot, PageSnapshot):
            raise WebStateError("snapshot must be a PageSnapshot")
        if len(snapshot.elements) > self.max_candidates:
            raise WebStateError("snapshot exceeds the search candidate bound")
        documents: list[SearchDocument] = []
        for ordinal, candidate in enumerate(snapshot.elements):
            if not isinstance(candidate, ElementCandidate):
                raise WebStateError("snapshot contains an invalid candidate")
            name_tokens = tokenize(candidate.accessible_name)
            role_tokens = tokenize(candidate.role)
            region_tokens = tokenize(candidate.region or "")
            documents.append(
                SearchDocument(
                    candidate=candidate,
                    ordinal=ordinal,
                    tokens=tuple(dict.fromkeys((*name_tokens, *role_tokens))),
                    region_tokens=region_tokens,
                )
            )
        return tuple(documents)


__all__ = ["CandidateExtractor", "SearchDocument", "tokenize"]
