"""Zero-prompt global workspace indexing and disk-local source inventory.

One install, central ~/.pie-global/projects/<workspace-id>/index.sqlite3.
No model calls, external network, shell execution or modifications to source trees.
A cheap stat walk determines changed files; only changed eligible content is read.
Python edits enter the real PIE AST/FTS/graph index via selected_paths.
Other languages have a bounded lexical text catalog, not fabricated AST support.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

from pie.indexing.indexer import index_project
from pie.indexing.global_lock import workspace_index_lock
from pie.scanning.discovery import IGNORED_DIRECTORIES, sensitive_name
from pie.scanning.ignore import IgnoreRules
from pie.storage.database import connect
from pie.storage.locations import global_home, project_id, workspace_file

WORKSPACE_MARKERS = frozenset({
    ".git", "pyproject.toml", "package.json", "Cargo.toml", "pom.xml",
    "go.mod", "CMakeLists.txt", "build.gradle", "build.gradle.kts",
    "settings.gradle", "setup.py", "project.godot", "Makefile",
})
# Inventory supports non-Python repositories as well; AST analysis remains Python-only.
SOURCE_SUFFIXES = frozenset({
    ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".java", ".kt", ".kts", ".c", ".h", ".cc", ".cpp", ".hpp",
    ".cs", ".go", ".rs", ".lua", ".rb", ".php", ".swift", ".dart",
    ".css", ".scss", ".html", ".glsl", ".vert", ".frag", ".osl",
    ".gd", ".shader", ".json", ".toml", ".yaml", ".yml", ".md",
    ".txt", ".sql", ".xml", ".gradle", ".sh", ".ps1", ".blend",
    ".blend1", ".blend2", ".fbx", ".obj", ".mtl", ".glb", ".gltf",
    ".usd", ".usda", ".usdc", ".vdb", ".png", ".jpg", ".jpeg",
    ".webp", ".exr", ".hdr", ".tif", ".tiff", ".wav", ".aiff",
    ".flac", ".mp3", ".ogg", ".als", ".adg", ".adv",
})
BINARY_ASSET_SUFFIXES = frozenset({
    ".blend", ".blend1", ".blend2", ".fbx", ".glb", ".usdc",
    ".vdb", ".png", ".jpg", ".jpeg", ".webp", ".exr", ".hdr",
    ".tif", ".tiff", ".wav", ".aiff", ".flac", ".mp3", ".ogg",
    ".als", ".adg", ".adv",
})
TEXT_CACHE_LIMIT = 128_000
FILE_HASH_LIMIT = 2_000_000
MAX_TRACKED_FILES = 20_000
RECONCILE_CHANGE_COUNT = 64
RECONCILE_FRACTION = .30
REPORT_PATH_LIMIT = 32


def _bounded_index_report(report: dict | None) -> dict | None:
    if report is None:
        return None
    reduced = dict(report)
    for field in ("changed_files", "removed_files"):
        names = list(reduced.get(field, []))
        reduced[field] = names[:REPORT_PATH_LIMIT]
        reduced[field + "_total"] = len(names)
        reduced[field + "_omitted"] = max(0, len(names) - REPORT_PATH_LIMIT)
    return reduced

INVENTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS pie_global_files(
    path TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL,
    size INTEGER NOT NULL, inode INTEGER NOT NULL,
    sha256 TEXT, content TEXT, text_state TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pie_global_files_path ON pie_global_files(path);
CREATE TABLE IF NOT EXISTS pie_global_changes(
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL, change_kind TEXT NOT NULL,
    old_sha256 TEXT, new_sha256 TEXT, observed_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pie_global_changes_recent ON pie_global_changes(seq DESC);
"""



def detect_workspace(start: Path) -> Path:
    """Find the *nearest* repository/project marker, never silently scan HOME."""
    start = Path(start).expanduser().resolve(strict=True)
    if start.is_file():
        start = start.parent
    if not start.is_dir():
        raise ValueError("Workspace must be an existing directory")
    home = Path.home().resolve()
    if start == home or start == Path(start.anchor):
        raise ValueError("Global PIE refuses HOME or a drive root as its workspace")
    for candidate in (start, *start.parents):
        if candidate == home and start != home:
            break
        if any((candidate / marker).exists() for marker in WORKSPACE_MARKERS):
            return candidate
    if start == home or start == Path(start.anchor):
        raise ValueError("Global PIE refused to index HOME or a drive root without a project marker")
    # A markerless explicit cwd is still a workspace, not a whole-drive scan.
    return start



def _eligible(path: Path) -> bool:
    return not sensitive_name(path) and path.suffix.lower() in SOURCE_SUFFIXES


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class GlobalWorkspaceIndex:
    """Central persistent workspace store with deterministic automatic refresh."""

    def __init__(self, root: Path, *, force_global: bool = False) -> None:
        self.root = detect_workspace(root)
        self._lock = threading.RLock()
        self.storage = workspace_file(self.root)
        if force_global and not os.environ.get("PIE_GLOBAL_STORAGE_ROOT"):
            raise ValueError("PIE_GLOBAL_STORAGE_ROOT must be configured for global mode")
        self.workspace_id = project_id(self.root)
        self.last_report: dict[str, Any] | None = None
        self.error: str | None = None
        self._refresh_count = 0

    def _db(self):
        db = connect(self.storage)
        db.executescript(INVENTORY_SCHEMA)
        return db

    def _scan(self) -> dict[str, tuple[int, int, int]]:
        rules = IgnoreRules(self.root)
        observed = {}
        def onerror(exc: OSError) -> None:
            raise OSError("Workspace directory unreadable during reconciliation") from exc
        for current, dirs, files in os.walk(self.root, topdown=True, onerror=onerror):
            folder = Path(current)
            dirs[:] = [name for name in sorted(dirs) if
                       name not in IGNORED_DIRECTORIES
                       and not (folder / name).is_symlink()
                       and not rules.ignored((folder / name).relative_to(self.root), is_directory=True)]
            for name in sorted(files):
                path = folder / name
                if not _eligible(path) or path.is_symlink():
                    continue
                relative = path.relative_to(self.root)
                if rules.ignored(relative):
                    continue
                try:
                    st = path.stat()
                except OSError as exc:
                    raise OSError("Workspace source metadata unavailable: " + str(relative)) from exc
                observed[relative.as_posix()] = (st.st_mtime_ns, st.st_size, st.st_ino)
                if len(observed) > MAX_TRACKED_FILES:
                    raise ValueError("Workspace exceeds 20000 eligible files; narrow the workspace")
        return observed

    def _capture(self, relative: str, stat: tuple[int, int, int]) -> tuple[str | None, str | None, str]:
        """Only read changed text; fail closed if a source changes mid-read."""
        source = self.root / relative
        if source.suffix.lower() in BINARY_ASSET_SUFFIXES or stat[1] > FILE_HASH_LIMIT:
            return None, None, "METADATA_ONLY"
        try:
            with source.open("rb") as stream:
                data = stream.read(FILE_HASH_LIMIT + 1)
            after = source.stat()
            if (after.st_mtime_ns, after.st_size, after.st_ino) != stat:
                raise RuntimeError("Source changed during global snapshot")
        except OSError as exc:
            raise RuntimeError("Cannot read changed source " + relative) from exc
        if len(data) > FILE_HASH_LIMIT:
            return None, None, "METADATA_ONLY"
        digest = sha256(data).hexdigest()
        if len(data) > TEXT_CACHE_LIMIT:
            return digest, None, "HASH_ONLY"
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return digest, None, "BINARY_OR_INVALID_UTF8"
        return digest, text, "INDEXED_TEXT"

    def refresh(self) -> dict[str, Any]:
        """Read file *metadata* globally, but only read/reparse changed source bytes."""
        with self._lock, workspace_index_lock(self.storage.parent / "index.lock"):
            t0 = time.perf_counter()
            try:
                current = self._scan()
                with closing(self._db()) as db:
                    records = db.execute(
                        "SELECT path,mtime_ns,size,inode,sha256 FROM pie_global_files"
                    ).fetchall()
                    previous = {
                        row["path"]: (row["mtime_ns"], row["size"], row["inode"])
                        for row in records
                    }
                    previous_hashes = {row["path"]: row["sha256"] for row in records}
                    old_ready = db.execute(
                        "SELECT value FROM metadata WHERE key='pie_global_ready'"
                    ).fetchone()
                new_paths = set(current) - set(previous)
                changed = {p for p in current if p not in previous or current[p] != previous[p]}
                deleted = set(previous) - set(current)
                first = old_ready is None
                dirty_count = len(changed | deleted)
                full = (first or dirty_count >= RECONCILE_CHANGE_COUNT
                        or (len(previous) >= 100 and dirty_count >= 16
                            and dirty_count / len(previous) >= RECONCILE_FRACTION))
                python_dirty = {
                    p for p in changed | deleted if p.lower().endswith(".py")
                }
                if not full and not changed and not deleted:
                    self._refresh_count += 1
                    self.error = None
                    self.last_report = {
                        "workspace_id": self.workspace_id, "root": str(self.root),
                        "storage": str(self.storage), "mode": "UNCHANGED",
                        "first_index": False, "changed_files": [], "deleted_files": [],
                        "scanned_file_metadata": len(current), "content_reads": 0,
                        "python_index": None,
                        "elapsed_ms": round((time.perf_counter()-t0)*1000, 3),
                        "measurement": "filesystem_operation_counts_not_model_tokens",
                    }
                    if self._refresh_count == 1:
                        self._register()
                    return self.last_report
                # Capture changed sources BEFORE modifying the previous good index.
                prepared = {p: self._capture(p, current[p]) for p in sorted(changed)}
                if full:
                    report = index_project(self.root)
                elif python_dirty:
                    report = index_project(self.root, selected_paths=python_dirty)
                else:
                    report = None
                # If a source changed between capture and indexing, fail closed.
                # The next background pass will reconcile from current bytes.
                for rel in changed:
                    target = self.root / rel
                    try:
                        st = target.stat()
                    except OSError as exc:
                        raise RuntimeError("Source disappeared during indexing") from exc
                    if (st.st_mtime_ns, st.st_size, st.st_ino) != current[rel]:
                        raise RuntimeError("Source changed during indexing: " + rel)
                with closing(self._db()) as db:
                    with db:
                        db.execute("BEGIN IMMEDIATE")
                        for p in sorted(deleted):
                            db.execute("DELETE FROM pie_global_files WHERE path=?", (p,))
                            if not first:
                                db.execute(
                                    "INSERT INTO pie_global_changes(path,change_kind,old_sha256,new_sha256,observed_utc)"
                                    " VALUES(?,?,?,?,?)",
                                    (p, "DELETED", previous_hashes.get(p), None, _utc()))
                        for p, stat in current.items():
                            if p not in prepared:
                                continue
                            digest, content, state = prepared[p]
                            if not first:
                                db.execute(
                                    "INSERT INTO pie_global_changes(path,change_kind,old_sha256,new_sha256,observed_utc)"
                                    " VALUES(?,?,?,?,?)",
                                    (p, "ADDED" if p in new_paths else "MODIFIED",
                                     previous_hashes.get(p), digest, _utc()))
                            db.execute(
                                "INSERT INTO pie_global_files(path,mtime_ns,size,inode,sha256,content,text_state) "
                                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
                                "mtime_ns=excluded.mtime_ns,size=excluded.size,inode=excluded.inode,"
                                "sha256=excluded.sha256,content=excluded.content,"
                                "text_state=excluded.text_state",
                                (p, *stat, digest, content, state),
                            )
                        db.execute(
                            "DELETE FROM pie_global_changes WHERE seq NOT IN "
                            "(SELECT seq FROM pie_global_changes ORDER BY seq DESC LIMIT 256)"
                        )
                        db.execute(
                            "INSERT INTO metadata(key,value) VALUES('pie_global_ready',?) "
                            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (_utc(),)
                        )
                # Global inventory is updated even for a non-Python project.
                self._refresh_count += 1
                self.error = None
                self.last_report = {
                    "workspace_id": self.workspace_id,
                    "root": str(self.root),
                    "storage": str(self.storage),
                    "mode": "FULL" if full else ("INCREMENTAL" if changed or deleted else "UNCHANGED"),
                    "first_index": first,
                    "changed_files": sorted(changed)[:REPORT_PATH_LIMIT],
                    "changed_files_total": len(changed),
                    "changed_files_omitted": max(0, len(changed) - REPORT_PATH_LIMIT),
                    "deleted_files": sorted(deleted)[:REPORT_PATH_LIMIT],
                    "deleted_files_total": len(deleted),
                    "deleted_files_omitted": max(0, len(deleted) - REPORT_PATH_LIMIT),
                    "scanned_file_metadata": len(current),
                    "content_reads": len(prepared),
                    "python_index": _bounded_index_report(report),
                    "elapsed_ms": round((time.perf_counter()-t0)*1000, 3),
                    "measurement": "filesystem_operation_counts_not_model_tokens",
                }
                self._register()
                return self.last_report
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {exc}"
                raise

    def _register(self) -> None:
        """Central registry stores only workspace locations and timestamps."""
        home = global_home()
        home.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(home / "registry.sqlite3", timeout=5)) as db:
            with db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS workspaces "
                    "(workspace_id TEXT PRIMARY KEY, root TEXT NOT NULL, last_seen_utc TEXT NOT NULL)")
                db.execute(
                    "INSERT INTO workspaces VALUES(?,?,?) "
                    "ON CONFLICT(workspace_id) DO UPDATE SET root=excluded.root,last_seen_utc=excluded.last_seen_utc",
                    (self.workspace_id, str(self.root), _utc()),
                )

    def status(self) -> dict[str, Any]:
        with self._lock:
            with closing(self._db()) as db:
                files = db.execute("SELECT COUNT(*) FROM pie_global_files").fetchone()[0]
                python_files = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
                status = db.execute(
                    "SELECT value FROM metadata WHERE key='index_state'").fetchone()
            return {
                "workspace_id": self.workspace_id,
                "root": str(self.root),
                "storage": str(self.storage),
                "tracked_files": files, "python_indexed_files": python_files,
                "python_index_state": status[0] if status else "UNINDEXED",
                "last_refresh": self.last_report,
                "refresh_count": self._refresh_count,
                "background_error": self.error,
                "model_calls": 0,
            }

    def recent_changes(self, *, limit: int = 12, max_chars: int = 4000) -> dict[str, Any]:
        """Automatically recorded file changes, independent of an agent."""
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be 1..50")
        if type(max_chars) is not int or not 500 <= max_chars <= 64000:
            raise ValueError("max_chars must be 500..64000")
        with self._lock:
            with closing(self._db()) as db:
                rows = db.execute(
                    "SELECT seq,path,change_kind,old_sha256,new_sha256,observed_utc "
                    "FROM pie_global_changes ORDER BY seq DESC LIMIT ?", (limit+1,)
                ).fetchall()
        events = [dict(item) for item in rows[:limit]]
        result = {"state":"COMPLETE" if len(rows)<=limit else "PARTIAL",
                  "events":events,"omitted":max(0,len(rows)-limit),
                  "source":"automatic_filesystem_fingerprint_log"}
        import json
        while len(json.dumps(result,ensure_ascii=False,separators=(",",":")))>max_chars and events:
            events.pop()
            result["omitted"]+=1
            result["state"]="PARTIAL"
        if len(json.dumps(result,ensure_ascii=False,separators=(",",":")))>max_chars:
            raise ValueError("Requested budget too small")
        return result

    def search(self, query: str, *, limit: int = 5, max_chars: int = 4000) -> dict[str, Any]:
        """Bounded multi-language lexical retrieval; recheck source SHA before use."""
        if not isinstance(query, str) or not 2 <= len(query.strip()) <= 128:
            raise ValueError("query must have 2..128 characters")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("limit must be 1..20")
        if type(max_chars) is not int or not 700 <= max_chars <= 64000:
            raise ValueError("max_chars must be 700..64000")
        with self._lock:
            with closing(self._db()) as db:
                # No regex/SQL interpolation of user input; LIKE escaped literals.
                term = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                records = db.execute(
                    "SELECT path,sha256,content,text_state FROM pie_global_files "
                    "WHERE lower(path) LIKE lower(?) ESCAPE '\\' OR "
                    "lower(content) LIKE lower(?) ESCAPE '\\' ORDER BY path LIMIT ?",
                    ("%" + term + "%", "%" + term + "%", limit + 1),
                ).fetchall()
            items=[]
            skipped=0
            for record in records[:limit]:
                if record["sha256"] and record["text_state"] != "METADATA_ONLY":
                    source=self.root / record["path"]
                    try:
                        with source.open("rb") as handle:
                            data=handle.read(FILE_HASH_LIMIT+1)
                        if sha256(data).hexdigest() != record["sha256"]:
                            skipped += 1
                            continue
                    except OSError:
                        skipped += 1
                        continue
                value=record["content"] or ""
                position=value.lower().find(query.strip().lower())
                excerpt=value[max(0,position-180):position+360] if position>=0 else value[:420]
                item={"path":record["path"],"sha256":record["sha256"],
                      "snippet":excerpt,"verification":"sha256_checked" if record["sha256"] else "metadata_only"}
                if len(str(item)) > max_chars:
                    skipped += 1
                    continue
                items.append(item)
            response={"state":"COMPLETE" if skipped == 0 and len(records) <= limit else "PARTIAL",
                      "matches":items,"omitted":skipped+max(0,len(records)-limit),
                      "note":"Text inventory only; no non-Python AST claims"}
            import json
            while len(json.dumps(response,ensure_ascii=False,separators=(",",":")))>max_chars and items:
                items.pop()
                response["omitted"]+=1
                response["state"]="PARTIAL"
            if len(json.dumps(response,ensure_ascii=False,separators=(",",":")))>max_chars:
                raise ValueError("Metadata cannot fit requested budget")
            return response
