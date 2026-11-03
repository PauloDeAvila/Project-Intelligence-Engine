"""Action-oriented evidence packs for code edits, without guessed dependencies."""
from __future__ import annotations

from pathlib import Path

from pie.retrieval.intelligence import smart_context, impact


def task_context(root: Path, query: str, *, max_chars: int = 12000,
                 limit: int = 8) -> dict[str, object]:
    """Retrieve edit targets and verified consumers, keeping citations explicit.

    Potential consumers are hints, not a claim of runtime impact. Tests are
    retrieved only when matching indexed evidence exists; no fabricated paths.
    """
    if not query.strip() or not 500 <= max_chars <= 200000 or not 1 <= limit <= 100:
        raise ValueError("invalid task context parameters")
    root=Path(root).resolve()
    primary=smart_context(root,query,max_chars=max_chars,limit=limit,include_body=True)
    fragments=[]
    impacts=[]
    seen=set()
    for evidence in primary["evidence"]:
        location=(evidence["path"],evidence["start_line"])
        if location in seen:
            continue
        seen.add(location)
        fragment=f'{evidence["path"]}:{evidence["start_line"]} [{evidence["symbol"]}]\n{evidence.get("content","")}'
        if len("\n\n".join(fragments+[fragment]))>max_chars:
            break
        fragments.append(fragment)
        if len(impacts)<3:
            try:
                result=impact(root,evidence["symbol"],limit=30,depth=1)
                impacts.append({"symbol":evidence["symbol"],
                                "verified_references":result["verified_references"],
                                "potential_consumers":result["transitive_consumers"][:10],
                                "affected_files":result["affected_files"][:20]})
            except (ValueError,KeyError):
                # No fabricated graph relationships on ambiguous symbols.
                pass
    payload="\n\n".join(fragments)
    return {"query":query,"context_state":primary["context_state"] if payload else "NO_MATCH",
            "content":payload,"context_characters":len(payload),
            "verified_impact_hints":impacts,"retrieval_method":primary["method"],
            "note":"Impact hints are potential consumers; run project tests before editing."}
