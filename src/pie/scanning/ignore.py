from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath


class IgnoreRules:
    """Apply the documented V0.1 subset of Git ignore rules, including nested files."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._rules: dict[Path, list[tuple[bool, bool, bool, tuple[str, ...]]]] = {}

    def _rules_for(self, base: Path) -> list[tuple[bool, bool, bool, tuple[str, ...]]]:
        if base in self._rules:
            return self._rules[base]
        rules: list[tuple[bool, bool, bool, tuple[str, ...]]] = []
        ignore_file = self.root / base / ".gitignore"
        try:
            raw_rules = ignore_file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            raw_rules = []
        for raw in raw_rules:
            line = raw.rstrip()
            if not line or line.startswith("#"):
                continue
            negated = line.startswith("!")
            if negated:
                line = line[1:]
            directory_only = line.endswith("/")
            anchored = line.startswith("/")
            line = line.rstrip("/")
            line = line.lstrip("/")
            if line:
                rules.append((negated, directory_only, anchored, tuple(PurePosixPath(line).parts)))
        self._rules[base] = rules
        return rules

    @classmethod
    def _glob_matches(cls, pattern: tuple[str, ...], path: tuple[str, ...]) -> bool:
        if not pattern:
            return not path
        if pattern[0] == "**":
            return cls._glob_matches(pattern[1:], path) or bool(path) and cls._glob_matches(pattern, path[1:])
        return bool(path) and fnmatch.fnmatchcase(path[0], pattern[0]) and cls._glob_matches(pattern[1:], path[1:])

    @classmethod
    def _rule_matches(
        cls,
        pattern: tuple[str, ...],
        path: tuple[str, ...],
        directory_only: bool,
        anchored: bool,
        is_directory: bool,
    ) -> bool:
        if len(pattern) == 1 and not anchored:
            for part in path:
                if fnmatch.fnmatchcase(part, pattern[0]):
                    return True
        for length in range(1, len(path) + 1):
            target = path[:length]
            target_is_parent = length < len(path)
            if directory_only and not (target_is_parent or is_directory and target == path):
                continue
            if cls._glob_matches(pattern, target):
                return True
        return False

    def ignored(self, relative: Path, is_directory: bool = False) -> bool:
        parts = relative.as_posix().strip("/").split("/")
        if not parts or parts == [""]:
            return False
        ignored = False
        for length in range(1, len(parts) + 1):
            current = tuple(parts[:length])
            current_is_directory = length < len(parts) or is_directory
            # Rules in a directory apply to its descendants. Deeper .gitignore
            # files are only considered when their parent was not excluded.
            for base_length in range(0, length):
                base = Path(*parts[:base_length]) if base_length else Path()
                scoped_path = current[base_length:]
                for negated, directory_only, anchored, pattern in self._rules_for(base):
                    if self._rule_matches(pattern, scoped_path, directory_only, anchored, current_is_directory):
                        ignored = not negated
            if ignored and current_is_directory:
                return True
        return ignored
