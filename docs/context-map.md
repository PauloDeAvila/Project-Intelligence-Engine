# Lightweight codebase context map

Maintain this map from inspected source only. Link to concrete files and symbols, not vague summaries. Update incrementally.

| Feature / concept | Entry points | Implementation | Callers / dependencies | Tests | Notes |
| --- | --- | --- | --- | --- | --- |
| File inventory | `pie.scanning.discovery.iter_files`, `discover_files` | `src/pie/scanning/discovery.py`, `src/pie/scanning/ignore.py` | `index_project` | `tests/test_pie_unit.py`, `tests/test_pie_integration.py` | Streams paths and one content snapshot at a time; reports unreadable paths so reconciliation preserves last known rows |
| Python symbols/imports | `pie.indexing.python_ast.parse_python` | `src/pie/indexing/python_ast.py` | `index_project` | `tests/test_pie_unit.py` | Syntax errors are reported, not raised |
| Persistent index | `pie.indexing.indexer.index_project` | `src/pie/indexing/indexer.py`, `src/pie/storage/database.py` | CLI | `tests/test_pie_integration.py` | SQLite rows reconcile by relative path/hash; legacy symbol uniqueness migrates to source-location uniqueness; scan state and diagnostics persist |
| CLI status | `pie.interfaces.cli.command_status` | `src/pie/interfaces/cli.py`, SQLite `metadata` | User/agent shell | `tests/test_pie_integration.py`, `tests/test_pie_e2e.py` | JSON counts, freshness state and structured diagnostics |
| CLI queries | `pie.interfaces.cli.main` | `src/pie/interfaces/cli.py` | User/agent shell | `tests/test_pie_e2e.py` | JSON output; semantic queries are future scope |
| Proof context | `pie.retrieval.evidence_atoms.build_proof_context` | `src/pie/retrieval/evidence_atoms.py` | MCP/CLI consumers; `build_context` | `tests/test_evidence_atoms.py` | Hash-backed atoms, adaptive clause selection, persistent cache and fail-closed delivery |
| Agent context routing | `pie.retrieval.context_mesh.ContextMesh.build` | `src/pie/retrieval/context_mesh.py` | `pie_build_context_mesh` MCP tool; future Cavecast coordinator | `tests/test_context_mesh.py` | Deduplicated facts/sources, isolated assignments, graph edges and local search/visualization |

## How to use
1. Find the requested behavior in this map.
2. Verify entries against source; the map can become stale.
3. Trace callers and consumers before modifying contracts.
4. Update only entries affected by confirmed changes.

## Context Pack v2

Exact function/qualified-method evidence is built in `retrieval/evidence.py`.
`retrieval/context_pack.py` separates returned verified-call completeness from
partial static coverage. `analysis/resolver.py` follows imports in lexical scopes;
`analysis/definitions.py` records name deletion positions. Consumers include MCP,
CLI and the evidence Gateway. Regressions: `test_static_call_coverage.py`,
`test_des04_context_pack.py`, `test_des04_mcp_stdio_e2e.py`; see
`des04-context-pack-mcp.md` for limitations and migration.
