# Project Intelligence Engine

PIE is a local, offline and persistent project index. Python repositories retain AST-based symbols, imports and relationships; the 3D ecosystem adapters also inventory and conservatively extract declarations/imports from C, C++, Objective-C, C#, Java, Kotlin, Haxe, GDScript, JavaScript, TypeScript and shader sources.

## Purpose

The repository retains its engineering governance foundation while providing a multilanguage indexing slice. Godot, Unreal, ArmorPaint and Blender project/assets are recorded as typed files, while binary assets remain metadata-only. Non-Python observations are explicitly marked in SQLite and are never presented as Python call-graph evidence.

## Getting started

Use Python 3.12+ from this repository root:

```text
python -m pie init --root path/to/project
python -m pie index --root path/to/project
python -m pie status --root path/to/project
python -m pie search cache --root path/to/project
```

`pie status` reports index freshness as `CURRENT`, `STALE`, `PARTIAL`, `ERROR`, or `UNINDEXED`, plus diagnostics from the latest indexing attempt. Review the state before relying on search results; an inaccessible file can leave previously indexed symbols available but marked `STALE`.

### 3D ecosystem coverage

The scanner recognizes engine and DCC files such as `.godot`, `.tscn`, `.tres`, `.uproject`, `.uplugin`, `.arm`, `.blend` and `.obj`, as well as common shader/configuration formats. Each indexed file receives a `parse_observations` record containing its adapter, status, capabilities, diagnostics, source hash and column encoding. This keeps the index useful for routing context without inventing unsupported semantic relationships.

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
python tools/benchmark_index.py --files 5000 --queries 100
python tools/benchmark_index.py --source path/to/real/project --queries 100
```
