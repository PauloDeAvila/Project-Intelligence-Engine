from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileRecord:
    path: Path
    sha256: str
    size: int
    language: str | None
    content: bytes


@dataclass(frozen=True)
class SymbolRecord:
    qualified_name: str
    name: str
    kind: str
    path: str
    start_line: int
    end_line: int
    start_col: int
    end_col: int


@dataclass(frozen=True)
class ImportRecord:
    module: str
    imported_name: str | None
    alias: str | None
    path: str
    line: int

