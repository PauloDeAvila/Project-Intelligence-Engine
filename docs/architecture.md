# Architecture and invariants

Record architecture as observed in the actual project. Avoid inventing aspirational layers.

## Components and responsibilities
| Component | Responsibility | Public contract | Depends on |
| --- | --- | --- | --- |
| `pie.scanning` | Discover eligible Python files and calculate hashes | Relative file inventory | `pathlib`, `hashlib` |
| `pie.indexing` | Parse Python AST and persist index records | Symbols/imports with source ranges | scanning, storage |
| `pie.storage` | Create SQLite schema and connections | Durable files/symbols/imports tables | SQLite |
| `pie.interfaces.cli` | Expose init/index/status/search/symbol | JSON on stdout, errors on stderr | indexing, storage |

## Dependency rules
- CLI depends on orchestration and storage; scanning does not depend on CLI.
- Source paths are relative POSIX-style strings; symbol ranges are one-based lines and zero-based columns from Python AST.
- SQLite is the only persisted artifact in `.pie/`; the source repository is read-only to PIE.

## Critical invariants
- Re-indexing the same unchanged file must preserve its row and avoid duplicate symbols/imports.
- Deleted files and their dependent rows must disappear from the current index.
- Parse failures remain observable through `files.parse_status`.

## Regression-sensitive workflows
- Init/index/status/search/symbol CLI journey: `tests/test_pie_e2e.py`.
- Hash/discovery/parser boundaries: `tests/test_pie_unit.py`.
- Persistence and deletion reconciliation: `tests/test_pie_integration.py`.
