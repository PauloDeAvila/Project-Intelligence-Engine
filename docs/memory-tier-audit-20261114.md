# PIE memory levels — repository audit (2026-11-14)

## Precise finding

There is no implemented, unified L0/L1/L2/L3 autonomous agent-memory
hierarchy in the protected main branch. Distinguish **context depth**
(map / context / source), **persistent structural index**, **cached
retrieval**, and **episodic task memory**. They are different facilities.

| Capability | Actual main implementation | Persistent? | What is verified |
| --- | --- | --- | --- |
| Structural/project map | .pie/index.sqlite3: paths, hashes, Python symbols/imports, graph evidence | Yes | Unit/integration/E2E and hash/freshness tests; static-only |
| Selected task context | FTS5/ranked retrieval, proof atoms, Context Packs, Context Mesh | Index and derived caches only | Budgeted retrieval and source hash checks; not agent episodic recall |
| Source depth | Source ranges under the indexed root with SHA-256 validation | Original source files | Provenance, bounded output; partial omissions are explicit |
| Warm-session retrieval | WarmContextService cache and in-process snapshots | No, process-local | Cached results check freshness; watcher is polling/stat based |
| Derived proof cache | .pie/evidence_atoms.sqlite3 | Yes | Generation/source-manifest invalidation; does not store model conversations |
| Agent task checkpoints | feat/pie-external-memory-stage1 | Branch only, **not in main** | CI tests passed at 531fb8433983a92ad549f652f2f5140791d6a2f1 |
| Search past tasks | feat/pie-external-memory-stage2 | Branch only, **not in main** | CI tests passed at 5790c350ead09232f8265be041c8fc6bb27fbefa |
| Automatic conversation capture, tier promotion/decay, cross-project recall | None proven | No | Not implemented/tested on main |
| Blender scene history | New Blender MCP proxy stores 32 raw observation snapshots | **No**, transient | Mock stdio test only; reset on restart |

## Memory stage 1 and stage 2 evidence

Stage 1 provides explicit task-start / task-record / task-resume
operations. Its test_pie_task_memory.py checks persistence across
reopening, event ordering, immutability after completion, bounded
histories, cross-project separation, CLI and MCP contracts, validation,
and symlink security.

Stage 2 builds on stage 1 with FTS5/lexical search, explicit provenance
status agent_supplied_unverified, bounded response budgets and omitted
counts. test_pie_task_search.py checks incremental events, persistence,
cross-project separation, safe query handling, FTS fallback, concurrent
initial indexing, CLI and MCP contracts.

The recorded CI checks on those branch heads passed, but the features
are **not in main** and this audit has **not executed their code inside
Blender or in the user's Codex installation**. Branch checks are not
release certification.

**Important:** records supplied by the agent are unverified claims.
Before reusing them as engineering facts, revalidate source references
against CURRENT SHA-256 code evidence. Do not silently promote notes or
decisions to verified code behavior.

## Proposed memory policy (not yet implemented)

- L0: session working set (minimal current objective and live tool results)
- L1: project map / ranked compact context (PIE SQLite + FTS5)
- L2: hash-backed exact source evidence with per-query expansion
- L3: explicit durable task checkpoints and retrieval, never automatic
  conversation spying; restrict to project and redact sensitive inputs

This is a **target policy**, not an implemented API named L0..L3.
To enable it, review and integrate stage1 and stage2 into main via PRs,
add a deterministic multi-session resume benchmark, and verify the
agent instructions actually call the memory MCP tools. Then measure
stale-reference rejection, recall, token overhead and user opt-in.

## Readiness gates

1. Merge/rebase stage1 + stage2 in the correct dependency order, reviewing
   SQL migrations and isolation. No blind cherry-picking over unrelated work.
2. Run both memory-specific test modules, then the full Python regression
   suite and existing CI on Linux and Windows.
3. Run create checkpoint -> stop agent -> new process -> retrieve/search ->
   validate referenced source SHA -> resume task against a pinned real repo.
4. Test source changes, ambiguous tasks, invalid/secret inputs, and zero
   cross-project leakage.
5. Expose explicit MCP instructions and measure actual model tokens and
   completion accuracy over repeated resumed tasks.

Until these gates pass, report the result as **experimental, not an
automatic durable memory system**.
