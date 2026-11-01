# Project Intelligence Engine

PIE V0.1 is a local, offline and persistent code index for Python repositories. It records source-file hashes, extracts Python symbols and imports, stores evidence in SQLite and exposes JSON CLI queries.

## Purpose

The repository retains its engineering governance foundation while providing the first functional indexing slice. Semantic references, graph traversal, Context Builder and MCP are later milestones.

## Getting started

Use Python 3.12+ from this repository root:

```text
python -m pie init --root path/to/project
python -m pie index --root path/to/project
python -m pie status --root path/to/project
python -m pie search cache --root path/to/project
```

## Repository layout

- `src/pie/` — scanner, AST indexer, SQLite storage and CLI.
- `tests/` — unit, integration and end-to-end coverage.
- `PROJECT.md` — V0.1 scope, contracts and verification matrix.
- `.agents/skills/` — reusable workflows with `SKILL.md` metadata and instructions.
- `docs/` — lightweight architecture, context map and decision log.
- `.github/pull_request_template.md` — review and verification checklist.

## Working agreement

Read before editing; separate observed facts from guesses; change the smallest coherent unit; run relevant checks; report changes and remaining risks. Never claim a test ran unless it actually ran.

## Usage note

Skills are instructions, not executable tooling. MCP connections, compilers, test runners, external accounts and credentials are deliberately not installed or embedded here. Configure them per project and per machine.

## Strict delivery governance
- `PONTO.md` defines evidence-driven read-only review and dependency/variable impact tracing.
- `.agents/skills/ci-bootstrap/` configures real tests, CI and branch protection **before features**.
- `.agents/skills/independent-review/` requires a detailed independent review report.
- `.github/workflows/ci.yml` runs the V0.1 regression and verification matrix.
- GitHub branch protection/rulesets are server-side repository settings and must be configured and verified separately for each cloned/template repository.

## Verification helpers

```text
python tools/check_install.py
python tools/benchmark_index.py
```
