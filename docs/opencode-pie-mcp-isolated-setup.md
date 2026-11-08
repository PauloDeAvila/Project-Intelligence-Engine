# Stage 5 — Register the real PIE MCP in an isolated OpenCode Windows process

The 117/117 Windows tests and Pyright success refer to prior commit
`6782f7e6`. They do **not** validate this configuration update or
the live OpenCode/Nemotron endpoint.

## Diagnosis

The user's running OpenCode process reported MCPs `pie-doctor-mesh`
and `9remote`, not `pie`. The orchestrator must **fail closed** in
this state; Doctor Mesh tool answers are not PIE evidence.

The PIE repository already provides the stdio MCP server:

```powershell
python -m pie.interfaces.mcp_server --root "C:\absolute\path\to\PIE"
```

OpenCode 1.x accepts a local MCP registration under `mcp.pie`
with `type=local`, an explicit command array and `enabled=true`.
The default `pie_mcp_name` on the orchestrator is `pie`.

## Isolated setup (do not restart the personal OpenCode process)

1. Create a separate clean Windows working copy of PR #39.
2. Use the **exact Python interpreter where PIE is installed**. In
   PowerShell, `(python -c "import sys; print(sys.executable)")`
   prints its path.
3. From the PIE working copy, generate a private config, specifying
   the exact same PIE checkout as the orchestrator's allowlisted root:

```powershell
$pieRoot = (Resolve-Path .).Path
$py = (python -c "import sys; print(sys.executable)").Trim()
$out = Join-Path $env:USERPROFILE ".pie-orchestrator\opencode-pie.json"
python tools/create_opencode_pie_config.py --root "$pieRoot" --python "$py" --output "$out"
```

The generator refuses to overwrite existing files or place its output
in the project root. Review the generated JSON before starting.

4. In a **new terminal/process**, not the existing personal OpenCode
   instance, set `OPENCODE_CONFIG` to `$out`, set a **new local**
   `OPENCODE_SERVER_PASSWORD` securely, and start a separate
   `opencode serve --hostname 127.0.0.1 --port 4097`.
   Do not use `--pure` without verifying that this OpenCode version
   loads the custom MCP configuration under that mode.
5. Check the isolated `/mcp` response locally using the new server
   password. It must show `pie: connected` (not only
   `pie-doctor-mesh`). Confirm the generated command points to the
   PIE project root and the MCP exposes `pie_project_status`.
6. Use a **separate private orchestrator JSON and SQLite path** for this
   test; set `opencode_url` to `http://127.0.0.1:4097`, choose the
   actual model identifier available in that isolated OpenCode process,
   and match its `projects[].root` with the generated MCP root.
   Leave `auto_execute=false` until the endpoint and permission
   behavior are independently checked.

The generated configuration requests `deny` for bash/edit/webfetch
and external-directory access. This **is not a host sandbox** and may
not deny tools introduced by other plugins or global configurations;
verify effective configuration and run as a low-privilege Windows user.

## Security and release gate

The Bearer that was posted in chat is publicly disclosed and is still
active by the user's account. **Rotate it and verify revocation before
any remote execution**. This change does not use, store or revoke it.

Never copy an MCP registration from Doctor Mesh and only change its
display name. The PIE MCP executable must use its own `--root` argument,
and local PIE freshness must independently match the tested project.

Run full unit/regression tests and Pyright, then one localhost-only
read-only test. Finally, after rotating and securing remote ingress,
allow one remotely dispatched task and check the SQLite state,
session ID, PIE MCP tool event and verified output. Keep PR in Draft
until the evidence exists.
