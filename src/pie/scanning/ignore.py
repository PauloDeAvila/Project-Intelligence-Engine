from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath


class IgnoreRules:
    """Small standard-library implementation of the .gitignore rules needed by V0.1."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.rules: list[tuple[bool, bool, bool, str]] = []
        path = root / ".gitignore"
        if not path.exists():
            return
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negated = line.startswith("!")
            if negated:
                line = line[1:]
            directory_only = line.endswith("/")
            line = line.rstrip("/")
            anchored = line.startswith("/")
            line = line.lstrip("/")
            if line:
                self.rules.append((negated, directory_only, anchored, line))

    @staticmethod
    def _matches(pattern: str, relative: str, anchored: bool) -> bool:
        candidates = [relative]
        if not anchored and "/" not in pattern:
            candidates.extend(PurePosixPath(relative).parts)
        for candidate in candidates:
            if fnmatch.fnmatchcase(candidate, pattern):
                return True
            if pattern.startswith("**/") and fnmatch.fnmatchcase(candidate, pattern[3:]):
                return True
        return False

    def ignored(self, relative: Path, is_directory: bool = False) -> bool:
        normalized = relative.as_posix().strip("/")
        ignored = False
        for negated, directory_only, anchored, pattern in self.rules:
            if directory_only:
                directory_match = normalized == pattern or normalized.startswith(pattern + "/")
                matches = directory_match
            else:
                matches = self._matches(pattern, normalized, anchored)
            if matches and (not directory_only or is_directory or normalized.startswith(pattern + "/")):
                ignored = not negated
        return ignored

