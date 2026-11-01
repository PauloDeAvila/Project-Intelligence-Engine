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
