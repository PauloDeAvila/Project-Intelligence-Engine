"""Context Mesh: distribute verified PIE evidence across cooperating agents.

The mesh is the boundary between a coordinating agent and specialist agents.
It does not execute filesystem or browser actions.  It resolves each agent's
proof obligations through PIE, deduplicates shared facts, and returns isolated
context packs plus a graph suitable for visualization or fast lookup.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable

from pie.retrieval.evidence_atoms import build_proof_context


MAX_AGENTS = 32
MAX_ID_CHARS = 96
MAX_OBJECTIVE_CHARS = 512


@dataclass(frozen=True)
class AgentRequest:
    """A narrow context request issued by the coordinator."""

    agent_id: str
    objective: str
    query: str
    requirements: tuple[str, ...] = ()
    limit: int = 12
    max_chars: int = 4000


def _clean_text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{field} must be a nonempty safe string <= {maximum} chars")
    return value.strip()


def _request(value: AgentRequest | dict[str, object]) -> AgentRequest:
    if isinstance(value, AgentRequest):
        return value
    if not isinstance(value, dict):
        raise ValueError("agent request must be an object")
    agent_id = _clean_text(value.get("agent_id", value.get("id")), "agent_id", MAX_ID_CHARS)
    objective = _clean_text(value.get("objective"), "objective", MAX_OBJECTIVE_CHARS)
    query = _clean_text(value.get("query"), "query", 4096)
    requirements_value = value.get("requirements", [])
    if not isinstance(requirements_value, list) or len(requirements_value) > 32:
        raise ValueError("requirements must be a list of at most 32 strings")
    requirements = tuple(
        _clean_text(item, "requirement", 128) for item in requirements_value
    )
    limit = value.get("limit", 12)
    max_chars = value.get("max_chars", 4000)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer in 1..100")
    if type(max_chars) is not int or not 500 <= max_chars <= 200000:
        raise ValueError("max_chars must be an integer in 500..200000")
    return AgentRequest(agent_id, objective, query, requirements, limit, max_chars)


def _source_id(path: str, source_sha256: str) -> str:
    return "source:" + sha256(f"{path}:{source_sha256}".encode("utf-8")).hexdigest()[:20]


def _fact_id(value: dict[str, object]) -> str:
    return "fact:" + str(value.get("id", ""))


class ContextMesh:
    """Build isolated agent packs over one shared, deduplicated evidence graph."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self._mesh: dict[str, object] | None = None

    def build(self, requests: Iterable[AgentRequest | dict[str, object]]) -> dict[str, object]:
        normalized = [_request(item) for item in requests]
        if not normalized:
            raise ValueError("at least one agent request is required")
        if len(normalized) > MAX_AGENTS:
            raise ValueError(f"at most {MAX_AGENTS} agent requests are supported")
        if len({item.agent_id for item in normalized}) != len(normalized):
            raise ValueError("agent_id values must be unique")

        agents: list[dict[str, object]] = []
        assignments: list[dict[str, object]] = []
        sources: dict[str, dict[str, object]] = {}
        facts: dict[str, dict[str, object]] = {}
        edges: dict[tuple[str, str, str], dict[str, str]] = {}

        for request in normalized:
            proof = build_proof_context(
                self.root,
                request.query,
                max_chars=request.max_chars,
                limit=request.limit,
                requirements=list(request.requirements),
                detail="compact",
            )
            agent_node = f"agent:{request.agent_id}"
            agents.append({
                "id": agent_node,
                "type": "agent",
                "label": request.agent_id,
                "objective": request.objective,
            })
            structured = proof.get("structured_facts", [])
            ready = proof.get("delivery", {}).get("can_deliver_atoms", False)
            assigned_fact_ids: list[str] = []
            assigned_source_ids: list[str] = []
            if ready and isinstance(structured, list):
                for fact in structured:
                    if not isinstance(fact, dict):
                        continue
                    fact_key = _fact_id(fact)
                    if not fact.get("verified"):
                        continue
                    facts.setdefault(fact_key, dict(fact, id=fact_key))
                    assigned_fact_ids.append(fact_key)
                    source_key = _source_id(str(fact.get("path", "")), str(fact.get("sha256", "")))
                    sources.setdefault(source_key, {
                        "id": source_key,
                        "type": "source",
                        "path": fact.get("path"),
                        "sha256": fact.get("sha256"),
                    })
                    assigned_source_ids.append(source_key)
                    edges[(agent_node, "requests", fact_key)] = {
                        "from": agent_node, "type": "requests", "to": fact_key,
                    }
                    edges[(fact_key, "grounded_in", source_key)] = {
                        "from": fact_key, "type": "grounded_in", "to": source_key,
                    }
            assignment_status = str(proof.get("delivery", {}).get("status", "BLOCKED"))
            assignments.append({
                "agent_id": request.agent_id,
                "objective": request.objective,
                "query": request.query,
                "status": assignment_status,
                "can_deliver": bool(ready),
                "fact_ids": list(dict.fromkeys(assigned_fact_ids)),
                "source_ids": list(dict.fromkeys(assigned_source_ids)),
                "obligations": proof.get("obligations", []),
                "missing": proof.get("coverage", {}).get("missing", []),
            })

        result = {
            "schema": "pie-context-mesh-v1",
            "status": "READY" if all(item["can_deliver"] for item in assignments) else "PARTIAL",
            "agents": agents,
            "assignments": assignments,
            "facts": list(facts.values()),
            "sources": list(sources.values()),
            "graph": {
                "nodes": agents + list(facts.values()) + list(sources.values()),
                "edges": list(edges.values()),
            },
            "deduplication": {
                "agent_count": len(agents),
                "unique_fact_count": len(facts),
                "unique_source_count": len(sources),
            },
            "coordinator_contract": {
                "model_role": "select_and_reason",
                "execution_role": "parent_orchestrator",
                "unverified_facts_delivered": False,
            },
        }
        self._mesh = result
        return result

    def search(self, query: str, *, limit: int = 20) -> dict[str, object]:
        """Search the already-built mesh without re-reading project files."""
        query = _clean_text(query, "query", 512).casefold()
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer in 1..100")
        if self._mesh is None:
            raise ValueError("build the context mesh before searching")
        candidates = []
        for node in self._mesh["graph"]["nodes"]:
            haystack = " ".join(str(node.get(key, "")) for key in ("id", "label", "path", "text", "objective")).casefold()
            score = sum(1 for token in query.split() if token in haystack)
            if score:
                candidates.append((score, node))
        candidates.sort(key=lambda item: (-item[0], str(item[1].get("id", ""))))
        return {"query": query, "results": [node for _, node in candidates[:limit]], "count": len(candidates)}

    def visualization(self) -> dict[str, object]:
        """Return graph-only data suitable for a UI, Mermaid adapter, or D3."""
        if self._mesh is None:
            raise ValueError("build the context mesh before requesting visualization")
        return self._mesh["graph"]


def build_context_mesh(root: Path, requests: Iterable[AgentRequest | dict[str, object]]) -> dict[str, object]:
    """Convenience API for a coordinator that needs one structured dispatch."""
    return ContextMesh(root).build(requests)
