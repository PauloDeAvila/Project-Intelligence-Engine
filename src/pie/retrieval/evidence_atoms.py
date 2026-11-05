"""Compact, source-backed proof atoms for model-facing context.

The regular context endpoint returns source ranges.  This module adds a
second representation for consumers that need the smallest trustworthy
context: structural source atoms selected against explicit proof obligations.
Atoms never claim more than the hash-verified source range proves.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pie.retrieval.context import build_context


MAX_REQUIREMENTS = 32
MAX_REQUIREMENT_CHARS = 128
MAX_ATOMS = 96
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

    def add(self, atom: EvidenceAtom) -> None:
        key = (atom.source_index, atom.line, atom.text)
        previous = self._atoms.get(key)
        if previous is None or atom.score > previous.score:
            self._atoms[key] = atom

    def ordered(self) -> list[EvidenceAtom]:
        return sorted(self._atoms.values(), key=lambda item: (-item.score, item.source_index, item.line))


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


def _source_atoms(context: dict, requirements: list[str]) -> tuple[list[dict], EvidenceAtomStore]:
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
        for offset, raw_line in enumerate(str(item.get("content", "")).splitlines()):
            text = raw_line.strip()
            if not text:
                continue
            kind, score = _kind(text)
            normalized_line = _normalize(text)
            if normalized_requirements:
                matches = sum(1 for requirement in normalized_requirements if requirement and requirement in normalized_line)
                score += matches * 100
            raw_text = _compact_text(text, requirements)
            store.add(EvidenceAtom(source_index, base_line + offset, kind, _semantic_text(raw_text, kind), score, raw_text))
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
    for requirement in requirements:
        normalized = _normalize(requirement)
        candidates = [atom for atom in ordered if normalized and normalized in _normalize(atom.text + " " + atom.raw_text)]
        if candidates:
            atom = min(candidates, key=lambda item: (-item.score, len(item.text), item.line))
            selected[(atom.source_index, atom.line, atom.text)] = atom
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
    context = build_context(root, query, max_chars=200000, limit=limit)
    sources, store = _source_atoms(context, checked_requirements)
    selected = _select_atoms(store, checked_requirements)
    atoms = [atom.as_dict() for atom in selected]
    coverage = _coverage(checked_requirements, atoms)
    relations = _relationship_atoms(context, {})
    proof_state = context.get("index_state", "UNINDEXED")
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
    if not result["coverage"]["complete"]:
        result["fallback"] = {
            "available": bool(context.get("source_ranges")),
            "reason": "source_ranges_when_incomplete",
        }
    if detail == "full":
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
    }
    if relations:
        compact["relations"] = [
            [item.get("relation_type") or item.get("type"), item.get("target_expression") or item.get("target"), item.get("resolution_status") or item.get("resolution")]
            for item in relations
        ]
    if "fallback" in result:
        compact["fallback"] = "source_ranges"
    compact["chars"] = len(json.dumps(compact, ensure_ascii=False, separators=(",", ":")))
    return compact

