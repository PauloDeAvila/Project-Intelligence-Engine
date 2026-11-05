"""Compact, source-backed proof atoms for model-facing context.

The regular context endpoint returns source ranges.  This module adds a
second representation for consumers that need the smallest trustworthy
context: structural source atoms selected against explicit proof obligations.
Atoms never claim more than the hash-verified source range proves.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pie.retrieval.context import build_context


MAX_REQUIREMENTS = 32
MAX_REQUIREMENT_CHARS = 128
MAX_ATOMS = 96
CACHE_SCHEMA_VERSION = "evidence-cache-v2"
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")


@dataclass(frozen=True)
class EvidenceAtom:
    """One compact fact with a stable source reference."""

    source_index: int
    line: int
    kind: str
    text: str
    score: int
    raw_text: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"s": self.source_index, "line": self.line, "kind": self.kind, "text": self.text, "raw": self.raw_text}


class EvidenceAtomStore:
    """Deduplicated atom collection with cost-aware selection."""

    def __init__(self) -> None:
        self._atoms: dict[tuple[int, int, str], EvidenceAtom] = {}
        self.total_added = 0
        self.duplicates = 0

    def add(self, atom: EvidenceAtom) -> None:
        self.total_added += 1
        key = (atom.source_index, atom.line, atom.text)
        previous = self._atoms.get(key)
        if previous is None or atom.score > previous.score:
            self._atoms[key] = atom
        else:
            self.duplicates += 1

    def ordered(self) -> list[EvidenceAtom]:
        return sorted(self._atoms.values(), key=lambda item: (-item.score, item.source_index, item.line))

    @property
    def unique_count(self) -> int:
        return len(self._atoms)


class EvidenceAtomCache:
    """Persistent, hash-invalidated cache shared by MCP subprocesses.

    The cache is deliberately separate from the PIE index database.  It stores
    derived proof atoms and completed proof responses, never authority about
    source files.  Every hit is checked against the current indexed generation
    and the on-disk SHA-256 manifest before it can be returned.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.path = self.root / ".pie" / "evidence_atoms.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path), timeout=5)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS proof_cache (
                cache_key TEXT PRIMARY KEY,
                generation TEXT NOT NULL,
                manifest TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS atom_cache (
                path TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                atoms TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY(path, source_sha256, start_line, end_line)
            );
            CREATE INDEX IF NOT EXISTS proof_cache_created_idx
                ON proof_cache(created_at);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "EvidenceAtomCache":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def generation(self) -> str:
        index_path = self.root / ".pie" / "index.sqlite3"
        if not index_path.is_file():
            return "UNINDEXED"
        conn = sqlite3.connect(str(index_path))
        try:
            metadata = conn.execute(
                "SELECT key,value FROM metadata ORDER BY key"
            ).fetchall()
            files = conn.execute(
                "SELECT path,sha256 FROM files ORDER BY path"
            ).fetchall()
        finally:
            conn.close()
        value = json.dumps(
            {"metadata": metadata, "files": files},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(value).hexdigest()

    def _manifest_valid(self, manifest: list[dict[str, str]]) -> bool:
        for item in manifest:
            relative = str(item.get("path", ""))
            expected = str(item.get("sha256", ""))
            if not relative or len(expected) != 64:
                return False
            candidate = self.root / relative
            try:
                resolved = candidate.resolve()
                if not resolved.is_relative_to(self.root) or candidate.is_symlink():
                    return False
                actual = sha256(resolved.read_bytes()).hexdigest()
            except OSError:
                return False
            if actual != expected:
                return False
        return True

    def get_proof(self, cache_key: str, generation: str) -> dict[str, object] | None:
        row = self.connection.execute(
            "SELECT generation,manifest,payload FROM proof_cache WHERE cache_key=?",
            (cache_key,),
        ).fetchone()
        if row is None or row[0] != generation:
            return None
        try:
            manifest = json.loads(row[1])
            payload = json.loads(row[2])
        except (TypeError, json.JSONDecodeError):
            self.connection.execute("DELETE FROM proof_cache WHERE cache_key=?", (cache_key,))
            self.connection.commit()
            return None
        if not isinstance(manifest, list) or not self._manifest_valid(manifest):
            self.connection.execute("DELETE FROM proof_cache WHERE cache_key=?", (cache_key,))
            self.connection.commit()
            return None
        return payload if isinstance(payload, dict) else None

    def put_proof(
        self,
        cache_key: str,
        generation: str,
        manifest: list[dict[str, str]],
        payload: dict[str, object],
    ) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO proof_cache "
            "(cache_key,generation,manifest,payload,created_at) VALUES (?,?,?,?,?)",
            (
                cache_key,
                generation,
                json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                time.time(),
            ),
        )
        self.connection.commit()

    def get_atoms(
        self,
        path: str,
        source_sha256: str,
        start_line: int,
        end_line: int,
    ) -> list[dict[str, object]] | None:
        row = self.connection.execute(
            "SELECT atoms FROM atom_cache WHERE path=? AND source_sha256=? "
            "AND start_line=? AND end_line=?",
            (path, source_sha256, start_line, end_line),
        ).fetchone()
        if row is None:
            return None
        try:
            atoms = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return None
        return atoms if isinstance(atoms, list) else None

    def put_atoms(
        self,
        path: str,
        source_sha256: str,
        start_line: int,
        end_line: int,
        atoms: list[dict[str, object]],
    ) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO atom_cache "
            "(path,source_sha256,start_line,end_line,atoms,created_at) VALUES (?,?,?,?,?,?)",
            (
                path,
                source_sha256,
                start_line,
                end_line,
                json.dumps(atoms, ensure_ascii=False, separators=(",", ":")),
                time.time(),
            ),
        )
        self.connection.commit()


def _normalize(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def _kind(line: str) -> tuple[str, int]:
    stripped = line.strip()
    lowered = stripped.casefold()
    if not stripped:
        return "blank", 0
    if lowered.startswith(("def ", "async def ", "class ")):
        return "definition", 75
    if lowered.startswith(("if ", "elif ", "else:", "try:", "except", "finally:", "for ", "while ", "with ")):
        return "guard", 70
    if lowered.startswith(("raise ", "return ", "yield ")):
        return "outcome", 68
    if lowered.startswith(("import ", "from ")):
        return "import", 60
    if any(token in lowered for token in (
        "sha256", "current", "stale", "partial", "unresolved", "verified", "additionalproperties",
        "max_chars", "max_calls", "limit", "exhaustive", "binding_key", "fingerprint",
    )):
        return "contract", 66
    if "(" in stripped and not lowered.startswith("#"):
        return "call", 52
    if "=" in stripped and not lowered.startswith(("==", ">=", "<=", "!=")):
        return "assignment", 48
    if lowered.startswith("#"):
        return "comment", 15
    return "detail", 25


def _compact_text(text: str, requirements: list[str]) -> str:
    text = " ".join(text.split())
    if len(text) <= 140:
        return text
    normalized = text.casefold()
    for requirement in requirements:
        position = normalized.find(requirement.casefold())
        if position >= 0:
            start = max(0, position - 48)
            excerpt = text[start:start + 120]
            return ("..." if start else "") + excerpt + ("..." if start + 120 < len(text) else "")
    return text[:120] + "..."


def _semantic_text(text: str, kind: str) -> str:
    lowered = text.casefold()
    if "sha256" in lowered and "==" in text:
        return "sha256_match => unchanged_file"
    if text == "continue":
        return "unchanged_file => skip_reprocessing"
    if "delete from files" in lowered:
        return "changed_file => delete_previous_file_record"
    if "run pie index first" in lowered:
        return "precondition: index_database_exists"
    if "index must be current" in lowered:
        return "precondition: index_state_current"
    if "relationships']" in lowered and "pop()" in lowered:
        return "budget_order: remove_relationships_first"
    if "source_ranges']" in lowered and "pop()" in lowered:
        return "budget_order: remove_source_ranges_next"
    if "diagnostics']" in lowered and "pop()" in lowered:
        return "budget_order: remove_diagnostics_last"
    if text.startswith("raise "):
        return "reject: " + text[6:][:96]
    if text.startswith("return "):
        return "return: " + text[7:][:96]
    if kind == "definition":
        return "definition: " + text[:150]
    if kind == "import":
        return "import: " + text[:100]
    if kind == "call":
        return "call: " + text[:150]
    if kind == "guard":
        return "guard: " + text[:104]
    if kind == "contract":
        return "contract: " + text[:140]
    return text[:120]


def _validate_requirements(requirements: list[str] | None) -> list[str]:
    if requirements is None:
        return []
    if not isinstance(requirements, list) or len(requirements) > MAX_REQUIREMENTS:
        raise ValueError(f"requirements must be a list of at most {MAX_REQUIREMENTS} strings")
    result = []
    for requirement in requirements:
        if not isinstance(requirement, str) or not requirement.strip() or len(requirement) > MAX_REQUIREMENT_CHARS:
            raise ValueError(f"each requirement must be a nonempty string of at most {MAX_REQUIREMENT_CHARS} chars")
        result.append(requirement.strip())
    return list(dict.fromkeys(result))


def _source_atoms(
    context: dict,
    requirements: list[str],
    cache: EvidenceAtomCache | None = None,
) -> tuple[list[dict], EvidenceAtomStore]:
    sources: list[dict] = []
    source_indexes: dict[tuple[str, str], int] = {}
    store = EvidenceAtomStore()
    normalized_requirements = [_normalize(item) for item in requirements]

    for item in context.get("source_ranges", []):
        path = str(item.get("path", ""))
        source_hash = str(item.get("sha256", ""))
        source_key = (path, source_hash)
        source_index = source_indexes.get(source_key)
        if source_index is None:
            source_index = len(sources)
            source_indexes[source_key] = source_index
            sources.append({"path": path, "sha256": source_hash, "symbol": item.get("symbol")})
        base_line = int(item.get("start_line", 1))
        end_line = int(item.get("end_line", base_line + len(str(item.get("content", "")).splitlines()) - 1))
        cached_atoms = cache.get_atoms(path, source_hash, base_line, end_line) if cache else None
        if cached_atoms is not None:
            # Older cache rows stored only a requirement-dependent excerpt.
            # They cannot safely serve a different clause, so rebuild them.
            cache_usable = all(isinstance(cached, dict) and cached.get("source_text") for cached in cached_atoms)
            if not cache_usable:
                cached_atoms = None
        if cached_atoms is not None:
            for cached in cached_atoms:
                source_text = str(cached.get("source_text", ""))
                kind = str(cached.get("kind", "detail"))
                base_score = int(cached.get("score", 0))
                raw_text = _compact_text(source_text, requirements)
                semantic_text = _semantic_text(raw_text, kind)
                normalized_line = _normalize(source_text)
                matches = sum(
                    1 for requirement in normalized_requirements
                    if requirement and requirement in normalized_line
                )
                store.add(EvidenceAtom(
                    source_index,
                    int(cached.get("line", base_line)),
                    kind,
                    semantic_text,
                    base_score + matches * 100,
                    raw_text,
                ))
            continue
        persisted_atoms: list[dict[str, object]] = []
        for offset, raw_line in enumerate(str(item.get("content", "")).splitlines()):
            text = raw_line.strip()
            if not text:
                continue
            kind, score = _kind(text)
            normalized_line = _normalize(text)
            base_score = score
            if normalized_requirements:
                matches = sum(1 for requirement in normalized_requirements if requirement and requirement in normalized_line)
                score += matches * 100
            raw_text = _compact_text(text, requirements)
            semantic_text = _semantic_text(raw_text, kind)
            line_number = base_line + offset
            store.add(EvidenceAtom(source_index, line_number, kind, semantic_text, score, raw_text))
            persisted_atoms.append({
                "line": line_number,
                "kind": kind,
                "text": semantic_text,
                "source_text": text,
                "score": base_score,
            })
        if cache and persisted_atoms:
            cache.put_atoms(path, source_hash, base_line, end_line, persisted_atoms)
    return sources, store


def _relationship_atoms(context: dict, source_indexes: dict[tuple[str, str], int]) -> list[dict]:
    atoms = []
    for relation in context.get("relationships", []):
        relation_type = relation.get("relation_type") or relation.get("type") or "RELATION"
        target = relation.get("target_expression") or relation.get("target") or ""
        status = relation.get("resolution_status") or relation.get("resolution") or "unknown"
        atoms.append({"kind": "relation", "type": relation_type, "target": target, "status": status})
    return atoms


def _coverage(requirements: list[str], atoms: list[dict]) -> dict[str, object]:
    haystack = " ".join(_normalize(str(atom.get("text", "")) + " " + str(atom.get("raw", ""))) for atom in atoms)
    matched = [requirement for requirement in requirements if _normalize(requirement) in haystack]
    missing = [requirement for requirement in requirements if requirement not in matched]
    return {"matched": matched, "missing": missing, "complete": not missing}


def _select_atoms(store: EvidenceAtomStore, requirements: list[str]) -> list[EvidenceAtom]:
    ordered = store.ordered()
    if not requirements:
        return ordered[:MAX_ATOMS]
    selected: dict[tuple[int, int, str], EvidenceAtom] = {}
    uncovered = set(range(len(requirements)))
    remaining = list(ordered)
    while uncovered and remaining:
        ranked: list[tuple[int, int, int, EvidenceAtom, set[int]]] = []
        for atom in remaining:
            haystack = _normalize(atom.text + " " + atom.raw_text)
            covers = {
                index for index in uncovered
                if _normalize(requirements[index]) and _normalize(requirements[index]) in haystack
            }
            if covers:
                ranked.append((len(covers), atom.score, -len(atom.text), atom, covers))
        if not ranked:
            break
        _, _, _, atom, covers = max(ranked, key=lambda item: (item[0], item[1], item[2], -item[3].line))
        selected[(atom.source_index, atom.line, atom.text)] = atom
        uncovered -= covers
        remaining = [candidate for candidate in remaining if candidate is not atom]
    # Proof obligations are the primary budget. Callers can request a larger
    # full-detail pack when they need surrounding structure; compact mode must
    # not spend the model budget on unrelated definitions.
    for atom in ordered:
        if len(selected) >= min(MAX_ATOMS, len(requirements)):
            break
        key = (atom.source_index, atom.line, atom.text)
        if key not in selected and atom.kind in {"definition", "guard", "outcome", "contract"}:
            selected[key] = atom
    return sorted(selected.values(), key=lambda item: (item.source_index, item.line))


def _cache_key(
    query: str,
    max_chars: int,
    limit: int,
    requirements: list[str],
    detail: str,
    generation: str,
) -> str:
    value = json.dumps(
        {
            "cache_schema": CACHE_SCHEMA_VERSION,
            "query": query,
            "max_chars": max_chars,
            "limit": limit,
            "requirements": requirements,
            "detail": detail,
            "generation": generation,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(value).hexdigest()


def _manifest(sources: list[dict]) -> list[dict[str, str]]:
    return [
        {"path": str(source.get("path", "")), "sha256": str(source.get("sha256", ""))}
        for source in sources
    ]


def _obligations(requirements: list[str], coverage: dict[str, object]) -> list[dict[str, object]]:
    matched = set(coverage.get("matched", []))
    return [
        {"clause": requirement, "status": "PROVEN" if requirement in matched else "MISSING"}
        for requirement in requirements
    ]


def _delivery_status(
    sources: list[dict],
    atoms: list[dict],
    coverage: dict[str, object],
    *,
    index_state: object,
    context_state: object,
) -> dict[str, object]:
    source_verified = all(
        str(source.get("path", "")) and len(str(source.get("sha256", ""))) == 64
        for source in sources
    )
    atoms_well_formed = all(
        int(atom.get("line", 0)) > 0 and bool(str(atom.get("text", "")).strip())
        for atom in atoms
    )
    if index_state != "CURRENT" or context_state != "CURRENT":
        status = "BLOCKED"
        reason = "source_or_index_state_not_current"
    elif not sources:
        status = "NOT_FOUND"
        reason = "no_verified_sources"
    elif not source_verified or not atoms_well_formed:
        status = "BLOCKED"
        reason = "invalid_source_or_atom_provenance"
    elif not coverage.get("complete", False):
        status = "FALLBACK_REQUIRED"
        reason = "proof_obligation_missing"
    else:
        status = "READY"
        reason = "all_obligations_verified"
    return {
        "status": status,
        "can_deliver_atoms": status == "READY",
        "source_verified": source_verified,
        "atoms_well_formed": atoms_well_formed,
        "fallback_required": status == "FALLBACK_REQUIRED",
        "reason": reason,
    }


def _structured_facts(sources: list[dict], atoms: list[dict]) -> list[dict[str, object]]:
    result = []
    for raw_atom in atoms:
        atom = (
            {"s": raw_atom[0], "line": raw_atom[1], "kind": raw_atom[2], "text": raw_atom[3]}
            if isinstance(raw_atom, list) and len(raw_atom) >= 4
            else raw_atom
        )
        source_index = int(atom.get("s", 0))
        source = sources[source_index] if 0 <= source_index < len(sources) else {}
        identity = f"{source.get('path', '')}:{source.get('sha256', '')}:{atom.get('line')}:{atom.get('text', '')}"
        result.append({
            "id": sha256(identity.encode("utf-8")).hexdigest()[:16],
            "source_index": source_index,
            "path": source.get("path"),
            "sha256": source.get("sha256"),
            "line": atom.get("line"),
            "kind": atom.get("kind"),
            "text": atom.get("text"),
            "verified": True,
        })
    return result


def build_proof_context(
    root: Path,
    query: str,
    *,
    max_chars: int = 4000,
    limit: int = 12,
    requirements: list[str] | None = None,
    detail: str = "compact",
) -> dict[str, object]:
    """Return a compact, hash-verified proof pack for a model-facing query.

    ``requirements`` are proof obligations, not answers.  When supplied, the
    pack prioritizes atoms that cover them and reports any obligation that was
    not found.  A caller must use the fallback path when ``complete`` is false.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a nonempty string")
    if type(max_chars) is not int or not 500 <= max_chars <= 200000:
        raise ValueError("max_chars must be 500..200000")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    if detail not in ("compact", "full"):
        raise ValueError("detail must be compact or full")
    checked_requirements = _validate_requirements(requirements)
    cache: EvidenceAtomCache | None = None
    generation = "CACHE_DISABLED"
    cache_key = ""
    try:
        try:
            cache = EvidenceAtomCache(root)
            generation = cache.generation()
            cache_key = _cache_key(query, max_chars, limit, checked_requirements, detail, generation)
            cached = cache.get_proof(cache_key, generation)
            if cached is not None:
                cached["cache"] = {
                    "persistent": True,
                    "hit": True,
                    "generation": generation,
                }
                return cached
        except (OSError, sqlite3.Error):
            if cache is not None:
                cache.close()
            cache = None

        context = build_context(root, query, max_chars=200000, limit=limit)
        sources, store = _source_atoms(context, checked_requirements, cache)
        selected = _select_atoms(store, checked_requirements)
        atoms = [atom.as_dict() for atom in selected]
        coverage = _coverage(checked_requirements, atoms)
        relations = _relationship_atoms(context, {})
        proof_state = context.get("index_state", "UNINDEXED")
        delivery = _delivery_status(
            sources,
            atoms,
            coverage,
            index_state=proof_state,
            context_state=context.get("context_state"),
        )
        result: dict[str, object] = {
            "schema_version": "pie-proof-context-v1",
            "status": "VERIFIED_STATIC_PROOF" if proof_state == "CURRENT" else "PARTIAL_STATIC_PROOF",
            "query": query,
            "index_state": proof_state,
            "relationship_state": context.get("context_state"),
            "sources": sources,
            "atoms": atoms,
            "relations": relations,
            "coverage": coverage,
            "obligations": _obligations(checked_requirements, coverage),
            "delivery": delivery,
            "selection": {
                "strategy": "adaptive_clause_set_cover",
                "candidate_count": store.unique_count,
                "selected_count": len(atoms),
                "deduplicated_count": store.duplicates,
            },
            "cache": {
                "persistent": cache is not None,
                "hit": False,
                "generation": generation,
            },
            "omitted": context.get("omitted", 0),
        }

        if detail == "full":
            # Full diagnostic packs obey the larger JSON budget. Compact packs are
            # budgeted after semantic projection so provenance metadata does not
            # evict the proof atoms needed by the model.
            while len(json.dumps(result, ensure_ascii=False, separators=(",", ":"))) > max_chars and result["atoms"]:
                current_atoms = result["atoms"]
                ranked = sorted(
                    range(len(current_atoms)),
                    key=lambda index: (
                        any(_normalize(requirement) in _normalize(str(current_atoms[index].get("text", "")) + " " + str(current_atoms[index].get("raw", ""))) for requirement in checked_requirements),
                        current_atoms[index].get("kind") in {"guard", "outcome", "contract", "definition"},
                        current_atoms[index].get("line", 0),
                    ),
                )
                removable = [index for index in ranked if not any(
                    _normalize(requirement) in _normalize(str(current_atoms[index].get("text", "")) + " " + str(current_atoms[index].get("raw", "")))
                    for requirement in checked_requirements
                )]
                current_atoms.pop(removable[0] if removable else ranked[0])
                result["coverage"] = _coverage(checked_requirements, current_atoms)
        result["used_chars"] = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        result["coverage"] = _coverage(checked_requirements, result["atoms"])
        result["obligations"] = _obligations(checked_requirements, result["coverage"])
        result["delivery"] = _delivery_status(
            sources,
            result["atoms"],
            result["coverage"],
            index_state=result["index_state"],
            context_state=result["relationship_state"],
        )
        result["structured_facts"] = _structured_facts(sources, result["atoms"])
        if not result["coverage"]["complete"]:
            result["fallback"] = {
                "available": bool(context.get("source_ranges")),
                "reason": "source_ranges_when_incomplete",
            }
        if detail == "full":
            if cache is not None:
                cache.put_proof(cache_key, generation, _manifest(sources), result)
            return result

        compact: dict[str, object] = {
            "schema": "pie-proof-context-v1",
            "status": result["status"],
            "state": result["index_state"],
            "sources": [
                [source.get("path"), str(source.get("sha256", ""))[:16], source.get("symbol")]
                for source in sources
            ],
            "facts": [
                [atom["s"], atom["line"], atom["kind"], atom["text"]]
                for atom in result["atoms"]
            ],
            "coverage": {
                "ok": result["coverage"]["complete"],
                "missing": result["coverage"]["missing"],
            },
            "obligations": result["obligations"],
            "delivery": result["delivery"],
            "selection": result["selection"],
            "cache": result["cache"],
        }
        if relations:
            compact["relations"] = [
                [item.get("relation_type") or item.get("type"), item.get("target_expression") or item.get("target"), item.get("resolution_status") or item.get("resolution")]
                for item in relations
            ]
        if "fallback" in result:
            compact["fallback"] = "source_ranges"
        compact["chars"] = len(json.dumps(compact, ensure_ascii=False, separators=(",", ":")))
        compact["structured_facts"] = _structured_facts(sources, compact["facts"])
        compact["chars"] = len(json.dumps(compact, ensure_ascii=False, separators=(",", ":")))
        if cache is not None:
            cache.put_proof(cache_key, generation, _manifest(sources), compact)
        return compact
    finally:
        if cache is not None:
            cache.close()

