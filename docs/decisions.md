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
