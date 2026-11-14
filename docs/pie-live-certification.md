# PIE Live: Codex token certification, RTK and Blender

Status: experimental on top of Phase-1 PR #72. No automatic paid model calls,
no automatic user configuration changes, and no claim of remote PC access.

## Evidence levels

1. Unit/CI: JSONL parser and deterministic oracle; synthetic inputs are not real token savings.
2. GitHub runners: genuine RTK binary (Linux and Windows), genuine Blender bpy (Linux, headless).
3. User Windows: genuine locally installed RTK, Codex and Blender via PowerShell probe.
4. Provider certification: paired real Codex sessions reporting turn.completed.usage.

Character reductions (or RTK gain estimates) are not provider token counts.
A GitHub runner is not the user's authenticated Windows Codex/Blender session.

## Windows first: no paid model calls

From the PIE checkout on branch feat/pie-live-token-certification-coverage-20261114:

    py -3.12 -m pip install -e .
    py -3.12 -m unittest discover -s tests -p test_pie_live_certification.py -v
    powershell -ExecutionPolicy Bypass -File tools/verify_windows_stack.ps1

The PowerShell script finds Blender on PATH or under Program Files, starts
Blender in background with an ephemeral cube and material, and checks real
Roughness changes with the PIE snapshot/delta code. It checks installed RTK
and Codex versions and audits ~/.codex/config.toml and hooks.json. It does not
save a .blend scene or spend Codex tokens.

Reports: %USERPROFILE%/pie-live-evidence/stack-report.json,
codex-route-audit.json. No raw config, credentials, prompts, JSONL,
or model answers are exported.

## Audit interception

    py -3.12 -m pie.certification.cli audit --codex-home "$env:USERPROFILE\.codex" --output "$env:USERPROFILE\pie-live-evidence\routes.json"

States: PIE_STDIO_WRAPPED, UNWRAPPED_STDIO, UNWRAPPED_HTTP, DISABLED and
UNKNOWN_CONFIGURATION. These refer to the configuration, not a verified
execution trace. Unknown shell commands pass through the RTK native hook;
native Codex tools and clients not routed via PIE are outside the proxy.

Universal interception is explicitly NEVER reported as certified. In
particular, HTTP/OAuth remote MCP and clients with native tool routes require
specific additional adapters. Do not silently replace existing MCP
registrations: preserve env/env_vars/cwd/permissions, credentials and timeouts.

## Real provider-reported tokens (this runs real paid/quota-consuming requests)

Prepare two different CODEX_HOME directories, both authenticated with your
own account, with equivalent permissions:

- Baseline: RTK hook disabled and MCP direct.
- Optimized: RTK hook enabled and MCP stdio tools routed through PIE.

These configuration profiles are NOT created automatically; copying auth
files or secrets is not authorized. Edit the model field of
benchmarks/live/pie-readonly-tool-scenario.json to a real supported model.
Use the same model, task, clean Git commit and deterministic oracle.

Invoke in PowerShell (one line):

    .\tools\run_live_codex_pairs.ps1 -Workspace "C:\Dev\Project-Intelligence-Engine" -Scenario ".\benchmarks\live\pie-readonly-tool-scenario.json" -BaselineCodexHome "$env:USERPROFILE\.codex-baseline" -OptimizedCodexHome "$env:USERPROFILE\.codex-optimized" -Repetitions 3

This makes SIX Codex calls (3 baseline, 3 optimized). All runs are read-only
and ephemeral, but remote MCP side effects are not necessarily prevented by
the Codex sandbox. Limit active MCP tools to read-only for benchmarking.

The output report is located at:
%USERPROFILE%/pie-live-evidence/provider-usage/paired-token-summary.json

It stores provider input_tokens, cached_input_tokens, output_tokens,
uncached_input_tokens, durations, exact-answer oracle results, and model/
config/commit hashes, but no raw prompts/answers/tool traces.

FAIL CLOSED: no turn.completed usage, mismatched model/config, unpaired data,
missing command/tool calls, incorrect oracle, model errors, fewer than
three trials -> NOT_CERTIFIED. A positive measured input reduction is
experimental evidence for that controlled scenario, not every model/task.

Costs are optional and based on your own actual USD per-million rates. Example
operator-created price JSON:
    {"input_per_million": 0.0, "cached_input_per_million": 0.0, "output_per_million": 0.0}
Replace the zeros with true prices before using the -Prices flag. This is a
tariff estimate, not an OpenAI invoice or subscription quota measure.

## Genuine Blender and RTK acceptance boundary

Blender probe: blender --background --factory-startup --python tools/blender_runtime_probe.py
It must emit PIE_BLENDER_LIVE_REPORT state PASS with INITIAL/UNCHANGED/DELTA
and a changed Roughness 0.35 to 0.28. This uses actual bpy but is not proof
of live Codex-to-Blender-MCP or graphics-driver/GUI support.

RTK 1.2.0 binary is tested in GitHub Actions using official release assets
checked against pinned SHA-256. That proves binary execution on runners, not
native hook interception of every terminal command on the user's machine.
