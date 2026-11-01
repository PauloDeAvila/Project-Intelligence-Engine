# Project Intelligence Engine — V0.1 project brief

## Purpose and supported functionality
PIE V0.1 is an offline, local and persistent index of Python repositories. It discovers eligible Python files, records content hashes, extracts classes/functions/methods/imports, persists the result in SQLite and exposes basic CLI queries.

Supported journey: `pie init` → `pie index` → `pie status` / `pie search` / `pie symbol`.

## In scope
- Python 3.12+ on Windows and Linux.
- Safe, incremental discovery below an explicit project root, excluding generated/dependency directories and oversized/non-Python files; preserve prior index rows for paths that could not be read on a scan.
- SHA-256 change detection and removal of deleted files from the index.
- AST-based Python symbols and imports with source line/column evidence.
- Reopenable SQLite persistence and JSON CLI output.

## Explicitly out of scope
- Semantic reference/call resolution, Tree-sitter, LSP and SCIP.
- Graph traversal, FTS5 ranking, Context Builder, glossary generation and MCP.
- Automatic code modification, network access and LLM dependencies.

## Stack and environments
- Python 3.12+, standard library only at runtime, SQLite, `unittest`, argparse and `ast`.
- CI runs the required verification check on Ubuntu and a compatibility job on Windows, both with Python 3.12. The code uses `pathlib` and avoids OS-specific path assumptions.

## Architecture and critical invariants
- CLI calls indexing and storage; the indexer owns discovery/parsing orchestration; SQLite is the durable derived index; source files are never modified.
- Every stored symbol belongs to one indexed file and carries a relative path plus source range.
- Indexing is atomic per invocation, deletes confirmed stale file rows, preserves rows for unreadable paths, and never invents semantic relationships.
- File content is hashed and parsed from one per-file snapshot; the indexer does not retain all file contents in memory together.
- `.gitignore` supports nested files, ordered negations, slash-scoped patterns, directory rules and `**`, `*`, `?`, and bracket wildcards. Git's escaped comment/negation markers and escaped trailing spaces are not supported by this standard-library subset.
- Relative paths are stored with `/` separators; only files below the requested root are considered.

## Acceptance criteria
- A temporary Python repository can be initialized, indexed, reopened and queried through the CLI.
- Classes, methods, functions, nested functions and imports are extracted with verifiable source locations.
- Changed and deleted files update the persistent index without a full manual reset.
- Invalid Python is retained as a file with an error parse status rather than crashing the index operation.
- All applicable CI matrix tiers and the complete regression suite pass.

## Mandatory verification matrix
Record actual commands and test coverage for every applicable tier. The agent must run all tiers AND the full existing repository suite after each implementation, not just tests for modified files.

| Layer | Commands / suite | Dependencies / prerequisites | Evidence expected |
| --- | --- | --- | --- |
| Basic functions / unit tests | `python -m unittest discover -s tests -p test_pie_unit.py -v` | Python 3.12+ | Pass/fail and counts |
| Component and subsystem | Not applicable in V0.1 | No separate component boundary | Reason in `ci/checks.json` |
| Integration and contracts | `python -m unittest discover -s tests -p test_pie_integration.py -v` | Python 3.12+ | Pass/fail and counts |
| Full user-flow / E2E | `python -m unittest discover -s tests -p test_pie_e2e.py -v` | Python 3.12+ | Pass/fail and counts |
| Full repository regression | `python -m unittest discover -s tests -v` | Python 3.12+ | All existing tests run |
| Build, lint, types, other applicable checks | `python tools/check_install.py` and `python -m compileall -q src tools tests` | Python 3.12+ | Install/import and compilation exit status |

## Verification policy
An implementation is NOT VERIFIED until the complete applicable matrix passes and objective results are recorded. Missing test infrastructure requires creation or explicit BLOCKED status; do not claim completion when verification cannot run. Do not assert absolute 100% correctness.

## Known risks and unresolved questions
- AST parsing is intentionally less language-general than the planned Tree-sitter adapter.
- Dynamic imports and semantic references remain unresolved by design.
- GitHub branch protection is a remote governance control; the active `Protect main` ruleset currently requires pull requests and the `Project Verification` check.
- The benchmark accepts `--files` and `--queries`, reports Python traced peak memory and repeated search time, and does not impose universal performance targets. Filesystem/path enumeration and SQLite's seen-path set still scale with project size.

## Bootstrap gate (mandatory before feature work)
- [x] Stack-specific dependencies and real test commands established
- [x] CI runs actual automated checks across all applicable levels
- [x] Missing automated coverage identified and addressed or explicitly blocked
- [x] GitHub PR/branch protection configured and independently confirmed
- [x] Required CI check named `Project Verification` configured for enforcement
- [ ] Independent review process configured using PONTO.md

Note: The starter workflow deliberately fails pending project-specific test configuration. This is NOT a runnable product test suite.
