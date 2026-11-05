# OpenCode 2.2.5 — isolated PIE MCP compatibility gate (PR #39)

## Facts verified against current OpenCode documentation

- `opencode serve` supports `--hostname` and `--port`; **DO NOT pass `--pure`**.
- `OPENCODE_CONFIG` supports a JSON file with `mcp.pie.type=local`,
  `command=[python,-m,pie.interfaces.mcp_server,--root,<PIE ROOT>]`,
  and `enabled=true`. This is the same MCP configuration schema
  used in 1.x; a new 2.x schema translation is **not** required on the
  basis of the published docs.
- Configurations are **merged** across global, custom and project
  paths. A private custom config is not an absolute sandbox.
- The supported HTTP routes include `GET /config`, `GET /mcp`,
  `GET /session/status`, `GET /experimental/tool/ids`,
  `POST /session`, `POST /session/:id/prompt_async` (204),
  and `GET /session/:id/message`.

Docs: https://opencode.ai/docs/cli ,
https://opencode.ai/docs/mcp-servers ,
https://opencode.ai/docs/server ,
https://opencode.ai/docs/config

## One-command Windows contract test (recommended)

In a clean copy of PR #39, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_opencode_pie_smoke.ps1 -PieRoot (Resolve-Path .).Path
```

The script creates a unique private config, starts an isolated OpenCode
on localhost port 4097 with a new random temporary password, checks
effective configuration/MCP/tool API, then **stops the temporary process**
and restores environment variables. No Nemotron inference, gateway
restart, tunnel change or remote task is performed.

If it reports `ready:false`, the effective OpenCode runtime contract
does not match the documented API. Keep the PR as Draft and inspect
the actual binary's `opencode serve --help` and localhost `/doc`.
Do not bypass failed checks to force a COMPLETED status.

## Windows procedure — no personal service restart, no external gateway

1. Open a **new PowerShell** in the clean PR #39 checkout, with
   Python 3.12+ and the PIE package installed in that interpreter.
   Do not perform a pull over the two uncommitted changes in the
   original workspace.

2. Create the custom config if not already present. Generator refuses
   overwrite; reuse an existing inspected file instead:

```powershell
$pieRoot = (Resolve-Path .).Path
$py = (python -c "import sys; print(sys.executable)").Trim()
$configFile = Join-Path $env:USERPROFILE ".pie-orchestrator\opencode-pie-2.json"
python tools/create_opencode_pie_config.py --root "$pieRoot" --python "$py" --output "$configFile"
```

3. Use only the **isolated new** terminal. The config remains private;
   other global MCPs may merge unless deliberately excluded from the
   effective runtime and permissions are checked:

```powershell
$env:OPENCODE_CONFIG = $configFile
$env:OPENCODE_SERVER_PASSWORD = [guid]::NewGuid().ToString("N")
$env:OPENCODE_SERVER_USERNAME = "opencode"
opencode --version
opencode serve --hostname 127.0.0.1 --port 4097
```

Keep that terminal open. Do not pass `--pure`.
Run the next command in another PowerShell **with the same private
OPENCODE_CONFIG and password conveyed through a secure local mechanism**;
never paste passwords into chat or source control:

```powershell
python tools/verify_opencode_runtime.py --url http://127.0.0.1:4097 --root "$pieRoot"
```

The preflight requires all of these before returning `"ready":true`:
- Effective `/config` contains a `mcp.pie` command bound to exactly
  the authorized PIE root with matching Python module and enabled=true.
- `/mcp` reports `pie.status=connected`.
- `/session/status` responds with the documented mapping shape.
- `/experimental/tool/ids` exposes `pie_project_status` (or its
  documented MCP-prefixed runtime name).
- Effective `/config.permission` contains explicit deny entries for
  shell, edit, web fetch and external directory.

This is **no-model/no-inference** preflight and does not touch the
gateway on port 8472 or tunnel. It does not attest that MCP responses
are factually correct, that a specific model exists, or that all plugin
capabilities are sandboxed.

4. Only once preflight returns `ready:true`:
   - In private orchestrator JSON set `opencode_url` to
     `http://127.0.0.1:4097`, `projects[].root` to `$pieRoot`,
     `pie_mcp_name` to `pie`, and use a real model from
     `opencode models`. Keep `auto_execute=false` until reviewed.
   - Run full regressions `python -m unittest discover -s tests -v`
     and `npx pyright`.
   - Rotate/revoke the **previously disclosed remote Bearer** and
     verify the old one fails before any public deployment.
   - Only then run a single authorized local read-only task and inspect
     session ID, PIE MCP tool output SHA-256, completed status and
     provider token metrics; migrate to remote only after local proof.

## Limitations

This commit provides a deterministic OpenCode API preflight. It does
not prove *the actual installed binary reporting 2.2.5* implements the
documented OpenCode routes until run on that Windows installation.
No completion or MCP connection is being claimed. The Draft PR must
remain unmerged until complete real validation.
