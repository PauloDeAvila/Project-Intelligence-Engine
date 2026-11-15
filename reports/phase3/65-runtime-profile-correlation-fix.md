# PIE Phase 3 — runtime profile correlation fix

## Finding

The optimized Codex run completed the expected MCP tools, but the gateway-owned lifecycle
file had no exact `run_id`/`pair_id` event. The capture previously placed `PIE_*` values only
in the parent Codex environment. That is insufficient when the Codex CLI does not forward
arbitrary environment variables to an MCP stdio child.

## Offline correction

`capture_codex` now materializes an ephemeral profile in the isolated Codex home for each run.
The profile preserves the selected MCP command and arguments, and adds an explicit server
`env` table containing only deterministic correlation and local telemetry fields:

- `PIE_RUN_ID`
- `PIE_PAIR_ID`
- `PIE_TASK_ID`
- `PIE_CONDITION`
- `PIE_APP`
- `PIE_SCENARIO_ID`
- `PIE_GATEWAY_SERVER`
- `PIE_GLOBAL_STORAGE_ROOT`
- `PIE_MCP_DIAGNOSTICS_PATH`

The effective profile name and its configuration hash are stored in the forensic manifest.
The original `config.toml`, original MCP registrations and credentials are not modified.

## Verification

- Runtime-profile unit test passed.
- Forensic/controller focused tests: 20 passed.
- `compileall`: passed.
- `git diff --check`: passed.
- PIE index remains `CURRENT` with `workspace_match=true`.

No model session or quota was consumed by this correction. The existing optimized run remains
non-certifying and is not retried automatically. A fresh authorized probe is required to
verify that the explicit profile produces exact gateway lifecycle correlation.
