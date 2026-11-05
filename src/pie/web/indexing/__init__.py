"""Local, deterministic search indexes for page snapshots."""

from .extractor import CandidateExtractor, SearchDocument, tokenize
from .models import RegionIndex, SearchMatch, SearchResponse
from .regions import RegionIndexer
from .roles import SemanticRoleMatcher
from .search import LocalWebSearch

__all__ = [
    "CandidateExtractor",
    "LocalWebSearch",
    "RegionIndex",
    "RegionIndexer",
    "SearchDocument",
    "SearchMatch",
    "SearchResponse",
    "SemanticRoleMatcher",
    "tokenize",
]
