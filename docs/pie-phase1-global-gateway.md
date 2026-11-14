# PIE Phase 1 — Global RTK + MCP Output Gateway

Status: experimental stacked PR on global PIE PR #65.
No code or GitHub CI run installs RTK, changes user Codex settings or executes
an unknown command on the user's computer.

## Independent delivery tasks

| Issue | Scope | Acceptance |
|---|---|---|
| #66 | Baseline | SQLite local per-tool character metrics; provider tokens remain null |
| #67 | Terminal/RTK | One subprocess invocation; preserve original return code |
| #68 | Fallback | Sanitized recovered output, strict limits and no silent success |
| #69 | MCP stdio | Forward protocol, preserve errors and structured output, recover pages |
| #70 | Global installer | Explicit dry-run, no overwrite of existing MCP servers |
| #71 | Certification | Linux/Windows CI, e2e synthetic fixture and observable evidence |

## Setup (Windows PowerShell, development version)

From the PIE checkout on the phase-1 branch:

    py -3.12 -m pip install -e .
    py -3.12 -m pie.gateway.install rtk-status
    py -3.12 -m pie.gateway.install install-rtk

The last command is a dry run. After installing the official RTK binary
separately and inspecting the native RTK hook configuration, activate it using:

    py -3.12 -m pie.gateway.install install-rtk --apply

It calls RTK's own rtk init -g --codex, and only after explicit --apply.
Do not install the hook twice into a client already using it.

## Terminal

Route a terminal invocation through:

    pie-terminal --rtk auto --max-chars 2500 -- git status
    pie-terminal --rtk off --max-chars 2500 -- python -m pytest -q

The wrapper uses shell=False, does not retry a command after failure, and
returns the original process exit code. It captures at most 200,000 bytes of
stdout and stderr each and labels incomplete capture CAPTURE_TRUNCATED.
The underlying result is sanitized before persistence in the global SQLite
project store. It is not a fully unredacted shell-recording service.

The native RTK hook can intercept supported Codex shell calls automatically,
but the PIE pie-terminal executable itself covers only calls explicitly
routed through it. An unsupported command that bypasses the wrapper does not
magically become visible to PIE. A future client-specific adapter is needed
to enforce universal routing across all terminal tools.

## MCP stdio proxy

Register an additional Codex MCP name by reviewing the dry-run first:

    pie-phase1 register-mcp --name guarded-blender --compress-tool get_scene_info --compress-tool get_object_info -- python -m blender_mcp.server

The upstream command above is an illustrative placeholder.
Replace it with the exact existing local Blender MCP launch command in Codex,
including interpreter and arguments, then run with --apply before --.

Verify with codex mcp get guarded-blender.

The stdio gateway:
- relays JSON-RPC notifications, requests and replies;
- adds pie_gateway_output_get to tools/list for paginated sanitized recovery;
- compacts text only for named tools when content is a single plain text block,
  structuredContent absent, outputSchema absent, no protocol/tool error;
- leaves images, mixed content, structured JSON, errors and unknown tools
  untouched, even when long (protocol correctness has priority);
- tracks only numeric metadata in SQLite, not full logs;
- uses existing seven-day/128-row/8MB sanitized output retention;
- never re-invokes the upstream tool.

For a long original over 500,000 characters, the gateway leaves the source
untouched rather than claim full recovery it cannot provide.

Caveat: a proxy registered as a second MCP server does not intercept calls
to the original server. To make it mandatory in an individual client, carefully
migrate the client's existing registration to the proxy, after recording and
backing up the real upstream command and verifying credentials and permissions.
This phase deliberately refuses silent global config replacement.

## Model-token and accuracy certification

pie-phase1 metrics --workspace <root> reports exact character counts,
not real prompt tokens, model accuracy, total session savings or cost.
The RTK rtk gain command may show estimates but is not provider usage.

Use real model usage traces and an independent task-correctness oracle to
certify an end-to-end economy claim. The baseline alone never certifies 85%.

Phase 1 is complete as an infrastructure test when all relevant CI checks
pass. Live Codex, Blender GUI and live provider token tests are separate gates.
