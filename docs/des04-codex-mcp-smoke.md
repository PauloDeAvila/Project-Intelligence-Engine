# DES-04 — Codex MCP integration smoke test (Windows)

Automated testing starts a real PIE stdio subprocess to prove the JSON-RPC
handshake and tool response. That is separate from a human-operated Codex
session choosing and calling the tool. Codex/model inference is never run in CI.

## 1. Update only the experimental worktree

    $wt = Join-Path $env:USERPROFILE 'pie-des04-validation'
    $py = Join-Path $env:USERPROFILE 'pie-dynamic-evidence-planner\.venv\Scripts\python.exe'
    git -C $wt fetch origin feat/des04-static-traceability-evaluation
    if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }
    git -C $wt merge --ff-only origin/feat/des04-static-traceability-evaluation
    if ($LASTEXITCODE -ne 0) { throw 'Fast-forward failed' }
    $env:PYTHONPATH = Join-Path $wt 'src'
    & $py -m unittest discover -s (Join-Path $wt 'tests') -p 'test_des04_mcp_stdio_e2e.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'MCP stdio integration failed' }

## 2. Prepare a disposable Requests workspace

A new copy is indexed; both the source snapshot and its previous SQLite index
remain untouched. Stop if destination already exists.

    $base = Join-Path $env:USERPROFILE 'pie-des04-evaluation'
    $origin = Join-Path $base 'snapshots\requests-v2.32.5'
    $target = Join-Path $env:USERPROFILE 'pie-des04-codex-smoke-requests'
    if (Test-Path -LiteralPath $target) { throw 'Destination already exists; choose another' }

    $env:PIE_COPY_ORIGIN = $origin
    $env:PIE_COPY_DEST = $target
    @'
    import os, shutil
    from pathlib import Path
    source = Path(os.environ["PIE_COPY_ORIGIN"])
    destination = Path(os.environ["PIE_COPY_DEST"])
    shutil.copytree(source, destination,
                    ignore=shutil.ignore_patterns(".git", ".pie", "__pycache__"))
    print(destination)
    '@ | & $py -
    if ($LASTEXITCODE -ne 0) { throw 'Source copy failed' }

    & $py -m pie.interfaces.cli init --root $target
    if ($LASTEXITCODE -ne 0) { throw 'Init failed' }
    & $py -m pie.interfaces.cli index --root $target
    if ($LASTEXITCODE -ne 0) { throw 'Index failed' }
    & $py -m pie.interfaces.cli context-pack extract_cookies_to_jar --root $target --max-chars 12000
    if ($LASTEXITCODE -ne 0) { throw 'Context Pack failed' }

## 3. Preview and register with Codex only when approved locally

The script runs in preview mode by default and refuses to overwrite an
existing MCP entry. The -Apply flag is the only mutation of Codex config.

    $script = Join-Path $wt 'tools\des04_register_codex_mcp.ps1'
    $parameters = @{
        ProjectRoot = $target
        PythonExe = $py
        SourceRoot = $wt
    }
    & $script @parameters
    # Examine printed paths before explicitly opting in:
    & $script @parameters -Apply

    codex mcp get pie-des04-preview --json
    codex mcp list

Behind the scenes, this uses the documented CLI command
codex mcp add <server-name> --env PYTHONPATH=<source-root>\src --
<python-executable> -u -m pie.interfaces.mcp_server --root <trusted-project>.

No Qwen/LM Studio call is required. The stdio server does not use the
existing Gateway HTTP port. The project root cannot be supplied by the model
through the context-pack tool arguments.

## 4. Validate an actual Codex tool invocation

Start a fresh Codex session or restart the IDE extension after registration.
In the Codex terminal UI, /mcp shows configured servers. Ask:

> Use the pie_build_context_pack MCP tool for extract_cookies_to_jar.
> Identify its six statically verified call sites in the Requests snapshot,
> citing source paths and lines. Do not claim these prove runtime breakage.
> Do not edit files.

Expected exploratory source sites on Requests v2.32.5:
- src/requests/adapters.py:365
- src/requests/auth.py:270
- src/requests/sessions.py:240
- src/requests/sessions.py:276
- src/requests/sessions.py:716
- src/requests/sessions.py:718

Report separately: CLI registration, stdio handshake, actual Codex model
tool invocation, grounded answer quality, and usage/token metrics if supplied.
An MCP server appearing in the list does NOT establish that the model used it.
The six sites are an exploratory observation, not independent frozen gold.

## 5. Optional removal

    codex mcp remove pie-des04-preview

Removal deletes only the preview MCP entry. The stable Gateway, DES-03
checkout and DES-04 historical baseline must remain untouched.
