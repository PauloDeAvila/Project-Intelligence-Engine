"""Fail-closed canonical evidence for exact Python symbol questions.

Facts are produced from a hash-verified source snapshot, not an LLM.  No
external dependencies, model calls or dynamic imports of analysed projects.
"""
from __future__ import annotations

import ast
import keyword
import time
from hashlib import sha256
from pathlib import Path

from pie.retrieval.symbols import find_definitions, find_references
from pie.storage.locations import workspace_file
from pie.storage.database import connect
from pie.retrieval.snapshot import SnapshotError, SnapshotVerifier


class EvidenceError(ValueError):
    """No trustworthy, unambiguous evidence is available."""



def _verify_project_snapshot(root: Path) -> dict:
    """Reject incomplete or globally drifted project snapshots.

    Unlike per-result hash checks, a reverse-lookup count also depends on files
    that did not appear in its result. A newly added caller must invalidate the
    count until reindexing. This deliberate full scan trades latency for safety.
    """
    started = time.perf_counter()
    db_started = time.perf_counter()
    connection = connect(workspace_file(root))
    try:
        indexed = {
            row["path"]: row["sha256"]
            for row in connection.execute("SELECT path,sha256 FROM files")
        }
    finally:
        connection.close()
    db_seconds = time.perf_counter() - db_started
    scan_started = time.perf_counter()
    try:
        verifier = SnapshotVerifier(root, indexed)
        result = verifier.verify()
    except SnapshotError as exc:
        raise EvidenceError(str(exc)) from exc
    scan_seconds = time.perf_counter() - scan_started
    metrics = getattr(verifier, "last_metrics", {})
    return {"db_seconds": round(db_seconds, 6), "discovery_hash_seconds": round(scan_seconds, 6),
            "files_checked": result.files_checked, "bytes_hashed": result.bytes_hashed,
            "total_seconds": round(time.perf_counter() - started, 6),
            "read_seconds": round(metrics.get("read_seconds", 0.0), 6),
            "hash_seconds": round(metrics.get("hash_seconds", 0.0), 6),
            "enumeration_seconds": round(metrics.get("enumeration_seconds", scan_seconds), 6)}


def _source_snapshot(root: Path, path: str) -> tuple[str, str]:
    root = root.resolve(strict=True)
    candidate = root / path
    if candidate.is_symlink():
        raise EvidenceError("Symlink source is not allowed")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise EvidenceError("Source escapes the project root")
    connection = connect(workspace_file(root))
    try:
        row = connection.execute("SELECT sha256 FROM files WHERE path=?", (path,)).fetchone()
    finally:
        connection.close()
    if row is None:
        raise EvidenceError("Source not indexed")
    raw = resolved.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != row["sha256"]:
        raise EvidenceError("STALE_SOURCE: source hash differs from index")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EvidenceError("Source is not valid UTF-8") from exc
    return text, digest


def _signature(source: str, line: int, name: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise EvidenceError("Cannot parse indexed source") from exc
    matches = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.lineno == line and node.name == name
    ]
    if len(matches) != 1:
        raise EvidenceError("Definition AST position is ambiguous or missing")
    node = matches[0]
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    arguments = ast.unparse(node.args)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
    return f"{prefix}{node.name}({arguments}){returns}:"


def build_evidence(root: Path, symbol: str, *, max_calls: int = 20) -> dict:
    """Return one verified canonical function and its bounded direct callers.

    This is intentionally limited to *exact, unambiguous* function definitions.
    Missing, stale and ambiguous results are errors, not empty authoritative facts.
    """
    if (not isinstance(symbol, str) or len(symbol) > 128
            or not all(part.isidentifier() and not keyword.iskeyword(part)
                       for part in symbol.split("."))):
        raise EvidenceError("Expected an exact Python identifier or qualified callable (max 128 chars)")
    if type(max_calls) is not int or not 1 <= max_calls <= 100:
        raise EvidenceError("Invalid max_calls")
    root = Path(root).resolve(strict=True)
    verification_metrics = _verify_project_snapshot(root)
    definitions = find_definitions(root, symbol, limit=500)
    if definitions.get("state") != "CURRENT":
        raise EvidenceError("Index/definitions are not CURRENT")
    if len(definitions.get("definitions", [])) >= 500:
        raise EvidenceError("Definition coverage truncated at the query limit")
    functions = [
        item for item in definitions.get("definitions", [])
        if (item["qualified_name"] == symbol if "." in symbol else item["name"] == symbol)
        and item["kind"] in ("function", "method")
        and item.get("declared_by") in ("def", "async_def")
    ]
    if not functions:
        raise EvidenceError("No verified function definition for this name")
    if len(functions) != 1:
        raise EvidenceError("AMBIGUOUS: multiple function definitions share this name")
    target = functions[0]
    source, digest = _source_snapshot(root, target["path"])
    signature = _signature(source, target["line"], target["name"])

    references = find_references(root, symbol, limit=500)
    if references.get("state") != "CURRENT":
        raise EvidenceError("References are not CURRENT")
    if references.get("count", 0) >= 500:
        raise EvidenceError("Reference coverage truncated at the query limit")
    matches = [
        row for row in references.get("references", [])
        if row.get("target") == target["binding"]
        and row.get("resolution") == "verified"
        and row.get("usage_kind") == "direct_call"
    ]
    # All reported consumers must match their indexed file hashes before publishing.
    checked = set()
    for row in matches:
        if row["path"] not in checked:
            _source_snapshot(root, row["path"])
            checked.add(row["path"])
    calls = [
        {"path": row["path"], "line": row["line"],
         "consumer_symbol": row.get("consumer_symbol"),
         "usage_kind": "direct_call", "resolution": "verified"}
        for row in matches[:max_calls]
    ]
    key = sha256((target["binding"] + ":" + digest).encode("utf-8")).hexdigest()[:20]
    return {
        "status": "VERIFIED",
        "symbol": symbol,
        "evidence_id": "pie:" + key,
        "binding": target["binding"],
        "path": target["path"],
        "line": target["line"],
        "end_line": target["end_line"],
        "signature": signature,
        "sha256": digest,
        "direct_call_sites": calls,
        "direct_call_count": len(matches),
        "direct_call_sites_omitted": max(0, len(matches) - max_calls),
        "coverage_note": (
            "Static, hash-checked direct calls only; dynamic dispatch, "
            "indirect aliases and external callers may not be covered."
        ),
        "verification_metrics": verification_metrics,
    }
