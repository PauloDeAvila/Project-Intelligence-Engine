# Architecture decision log

Record decisions that affect multiple components or have non-obvious tradeoffs. Do not generate decisions for every minor edit.

## ADR template
- Date:
- Status: proposed / accepted / superseded
- Problem and constraints:
- Alternatives considered:
- Decision:
- Consequences and compatibility:
- Verification:

## ADR-001 — V0.1 uses Python AST and SQLite
- Date: 2026-10-31
- Status: accepted
- Problem and constraints: Prove the local indexing architecture with an offline, standard-library MVP before adding language-server or graph dependencies.
- Alternatives considered: Tree-sitter and a dedicated graph database were deferred because the first acceptance criteria only require Python symbols/imports and durable queries.
- Decision: Use `ast` for Python extraction and relational SQLite tables for files, symbols and imports. Keep source paths and source ranges as evidence.
- Consequences and compatibility: V0.1 is Python-only and does not resolve semantic calls/references. Later adapters must preserve the evidence-oriented storage contract.
- Verification: Unit, integration, E2E, full regression and compile checks pass locally; see `docs/review-report.md`.

## ADR-002 — Persist index freshness and scan diagnostics
- Date: 2026-11-01
- Status: accepted
- Problem and constraints: preserving rows after transient file/directory access errors prevents data loss but can make obsolete symbols appear current to callers.
- Alternatives considered: delete inaccessible rows (loses last-known data); expose scan errors only in the immediate `index` response (lost across process boundaries); persist the last scan state and diagnostics in the existing metadata table.
- Decision: persist `index_state` and structured diagnostics in `metadata`, include them in index results and `pie status`, report both per-path failures and an aggregate `files_not_processed` count, and classify completed scans as `CURRENT`, `STALE`, or `PARTIAL`; persist `ERROR` if an indexing transaction fails and `UNINDEXED` before the first scan.
- Consequences and compatibility: existing SQLite databases require no schema migration because metadata is key/value; callers consuming status JSON gain `index_state` and `diagnostics` fields. Consumers must inspect state before treating results as fresh.
- Verification: integration and E2E tests cover stale preservation, partial omissions, parser errors, fatal transaction errors and recovery; `.gitignore` tests compare the documented common subset against `git check-ignore`.

## ADR-003 — Preserve repeated symbol definitions by source location
- Date: 2026-11-01
- Status: accepted
- Problem and constraints: real Python repositories can define the same qualified name and kind more than once in a file, including property accessors. The original SQLite uniqueness constraint rejected such valid source during indexing.
- Alternatives considered: keep one row and lose source evidence; skip or mark affected files partial; migrate the symbol key to include source start line and column.
- Decision: key symbols by file, qualified name, kind, start line and start column. On opening a legacy database, rebuild the symbols table transactionally while copying all existing records, then recreate its indexes.
- Consequences and compatibility: existing databases are migrated automatically and retain existing rows. Search can return multiple location-bearing rows for one name. Migration relies on SQLite transactional DDL; insufficient database permissions or a locked database prevents opening the index and surfaces the error.
- Verification: integration tests construct the legacy schema, confirm data preservation and foreign-key integrity after migration, and index repeated property getter/setter definitions without dropping either location.

## ADR-004 — Hash-backed Evidence Atoms are a derived retrieval layer
- Date: 2026-11-05
- Status: accepted
- Problem and constraints: sending complete source ranges to an LLM wastes context while a compact representation must not lose provenance or silently claim coverage.
- Alternatives considered: truncate raw ranges without validation; cache only in memory; or expose compact facts without a fallback signal.
- Decision: project hash-verified ranges into clause-selected Evidence Atoms, persist derived atoms and proof responses in `.pie/evidence_atoms.sqlite3`, invalidate by index generation and source SHA-256, and expose `READY`/`FALLBACK_REQUIRED` delivery states.
- Consequences and compatibility: existing `pie_build_context` remains available; proof consumers gain structured obligations, coverage and provenance. The cache is disposable and never authoritative over the index.
- Verification: `tests/test_evidence_atoms.py` covers cache hits, source invalidation, structured delivery and missing obligations; full project regression passes.

## ADR-005 — Context Mesh separates coordination from execution
- Date: 2026-11-05
- Status: accepted
- Problem and constraints: multiple agents need different slices of one project context without each re-reading the repository or receiving unverified facts.
- Alternatives considered: share complete files with every agent; let each agent query independently; or create a central graph with no per-agent delivery gate.
- Decision: `ContextMesh` builds isolated assignments from verified proof contexts, deduplicates shared facts/sources, exposes graph edges and local search, and refuses to deliver incomplete atoms as `READY`. File/browser actions remain outside this layer for the future Cavecast parent coordinator.
- Consequences and compatibility: coordinators can consume `pie-context-mesh-v1` through the `pie_build_context_mesh` MCP tool; static graph edges describe evidence and routing, not runtime behavior.
- Verification: `tests/test_context_mesh.py` covers shared-source deduplication, graph search/visualization, incomplete-proof rejection and the MCP contract.
