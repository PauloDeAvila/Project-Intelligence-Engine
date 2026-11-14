# PIE Global — zero-prompt indexing and central memory (experimental)

Status: PR #65, stacked on #64 and #63. Not merged/released.
Design: **no model action is required** for indexing and invalidation.

## What "global" means

There is one install and one MCP registration per supported client, **not
a per-project setup**. The MCP subprocess discovers its workspace from its
working directory (or an explicit operator-supplied --workspace parameter),
starts its index automatically, polls the filesystem, and refreshes again
*before each tool call*. You do not ask an LLM to run index commands.

Project indexes are logically isolated (avoids cross-project symbol pollution)
but physically stored in one central user-owned location:

- Windows: C:\Users\<user>\.pie-global\registry.sqlite3
- Windows: C:\Users\<user>\.pie-global\projects\<hash>\index.sqlite3
- Linux/macOS: ~/.pie-global/registry.sqlite3 and projects/<hash>

The source repository remains unmodified: no project-local .pie directory is
created by global mode. Existing "pie", "pie-setup" and "pie-mcp" behavior
remains project-local when global mode is not active.

This is not permission for an entire-disk crawl. Only workspaces opened by
a client (or explicitly passed on the command line) are indexed. HOME and
drive roots without project markers are rejected to prevent accidental
scanning of personal data.

## One-time Windows/Codex setup

Run from your PIE checkout (PowerShell):

~~~powershell
git fetch origin
git switch feat/pie-global-zero-touch-index-20261114
py -3.12 -m venv "$env:USERPROFILE\.pie-global\venv"
& "$env:USERPROFILE\.pie-global\venv\Scripts\python.exe" -m pip install -e .
& "$env:USERPROFILE\.pie-global\venv\Scripts\pie-global.exe" install-codex
codex mcp get pie-global
~~~

This deliberately asks the Codex CLI to register the command **once** in
the user's global MCP configuration. It will not overwrite an existing
server named pie-global. The registration uses the absolute virtualenv
Python executable, so PIE remains available from other project folders.
Keep the PIE checkout at its installed location while using an editable
installation. For durable deployment, install a pinned package/wheel
rather than relying on an editable checkout.

To check one workspace explicitly (without asking any agent):

~~~powershell
& "$env:USERPROFILE\.pie-global\venv\Scripts\pie-global.exe" scan --workspace "C:\Dev\MyGame"
& "$env:USERPROFILE\.pie-global\venv\Scripts\pie-global.exe" status --workspace "C:\Dev\MyGame"
& "$env:USERPROFILE\.pie-global\venv\Scripts\pie-global.exe" projects
~~~

To maintain an always-running watcher independently of Codex, you can
run the optional command below in a dedicated terminal or register it
with Windows Task Scheduler yourself:

~~~powershell
& "$env:USERPROFILE\.pie-global\venv\Scripts\pie-global.exe" watch --workspace "C:\Dev\MyGame" --poll-seconds 5
~~~

The watcher command watches a single explicitly chosen workspace.
The global MCP starts a watcher per active client session by default.

## Automatic lifecycle

1. Workspace opened: resolve nearest .git / pyproject.toml / package.json /
   Cargo.toml / other recognized root. No prompt.
2. On first open: discover eligible files and index Python AST/definitions/
   FTS/graph. Record file hashes and source metadata for other languages.
3. On subsequent access: enumerate supported file paths and read metadata
   (mtime_ns, size and inode). If unchanged, no source content reads,
   no reindex and no SQLite content rewrite.
4. If one Python file changes: read/reparse that file only, preserve all
   other source rows, refresh affected analysis, update metadata.
5. File deleted: remove its stale records. Changes in bulk trigger
   a full reconcile.
6. Background watch polls every five seconds while MCP is open; a refresh
   is also forced before each model tool call. Both paths are deterministic
   Python code, not model choices. Multiple processes serialize refresh
   with an OS-level advisory file lock.
7. When the process closes, the central SQLite files survive. Reopening
   the same workspace reuses the existing index.

The metadata-based fast path cannot detect a file whose content is
modified and whose file size, mtime and inode are all deliberately
restored. A full reconciliation or explicit scan can re-verify content.
For security-critical source claims, PIE's existing SHA-verified evidence
paths still check source bytes before presenting evidence as current.

## Language coverage

- Python .py: semantic AST, definitions/references and evidence packs.
- TypeScript, JavaScript, Java, C, C++, C#, Go, Rust, shader code,
  Lua, YAML, TOML, markdown and other listed text formats: **path and
  bounded lexical source search**, persisted with SHA-256 verification.
- Blender .blend, FBX, GLB, EXR and Ableton .als binary assets: metadata-only tracking. Scene/material
  semantic observation still requires the separate Blender MCP bridge.
- Files excluded by .gitignore, common credential filenames, symlinks
  and generated directories are skipped.

Do **not** infer native TypeScript/C++ call graphs, equivalent feature
coverage, or complete Blender scene awareness from lexical indexing.
For those languages semantic parsers are a separate development step.

## MCP tools

The existing compact profile remains available; Global PIE exposes:
- pie_global_status — central index lifecycle, last refresh and counts.
- pie_global_find_files — bounded lexical search with hash validation.
- pie_global_recent_changes — small, automatic change-event journal with old/new hashes (up to 256 recent events, no agent-written checkpoints needed).
- plus current PIE gateway, checkpoints and proof/context MCP tools.

The global registry tracks which workspaces have actually been opened; run the
"projects" command to inspect it without crawling the entire computer.

An LLM may choose never to query these tools, so an automatic index does
not guarantee an automatic *token-saving retrieval policy*. The essential
difference is that indexing, refreshing, storing and invalidation never
depend on a prompt. End-to-end token reduction requires instrumenting
the Codex client/adapter and measuring provider-reported usage.

## Explicit test commands

~~~powershell
python -m unittest discover -s tests -p test_pie_global_workspace.py -v
python -m unittest discover -s tests -v
python tools/verify_project.py
python -m compileall -q src tools tests
~~~

Before production merge, verify actual Codex global MCP registration
inherits the requested workspace CWD on Windows. If a client launches
MCP from a fixed directory, provide its documented workspace environment
or install a client-specific workspace adapter; NEVER silently index the
user's HOME as a fallback. Do not infer successful real-client setup from
the simulated MCP stdio acceptance tests in CI.
