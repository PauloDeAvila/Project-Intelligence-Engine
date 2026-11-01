# Lightweight codebase context map

Maintain this map from inspected source only. Link to concrete files and symbols, not vague summaries. Update incrementally.

| Feature / concept | Entry points | Implementation | Callers / dependencies | Tests | Notes |
| --- | --- | --- | --- | --- | --- |
| File inventory | `pie.scanning.discovery.discover_files` | `src/pie/scanning/discovery.py`, `src/pie/scanning/ignore.py` | `index_project` | `tests/test_pie_unit.py` | Applies `.gitignore`, excludes generated dirs and non-Python files |
| Python symbols/imports | `pie.indexing.python_ast.parse_python` | `src/pie/indexing/python_ast.py` | `index_project` | `tests/test_pie_unit.py` | Syntax errors are reported, not raised |
| Persistent index | `pie.indexing.indexer.index_project` | `src/pie/indexing/indexer.py`, `src/pie/storage/database.py` | CLI | `tests/test_pie_integration.py` | SQLite rows reconcile by relative path/hash |
| CLI queries | `pie.interfaces.cli.main` | `src/pie/interfaces/cli.py` | User/agent shell | `tests/test_pie_e2e.py` | JSON output; semantic queries are future scope |

## How to use
1. Find the requested behavior in this map.
2. Verify entries against source; the map can become stale.
3. Trace callers and consumers before modifying contracts.
4. Update only entries affected by confirmed changes.
