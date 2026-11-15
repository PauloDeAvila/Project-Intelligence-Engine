# Phase 3 — task-level usage and real provider certification

Experimental branch based on PR #81. **No authenticated Codex session has been run by this change.**

## What is measured automatically

Every gateway call already sent to `pie.gateway.metrics.record` now also writes
a bounded local task ledger. The fields are app, task ID, tool, state,
character counts and elapsed time. No prompt, response, page contents or
credentials are stored in this ledger.

Applications are inferred from MCP tool names: Blender and Playwright/web.
For an explicit domain override, set `PIE_APP=blender` or `PIE_APP=web`.
Set `PIE_TASK_ID` to a non-sensitive identifier before launching the
gateway process; inherited environment variables are captured at each call.
Without it, the task is `unassigned`. **Environment variables must be set
in the process launching the MCP server, not only in a later shell.**

The ledger does not instrument Codex native browser tools, non-PIE MCP
servers or unwrapped terminal commands. No universal monitoring claim.

## Windows setup

On the phase-3 branch in a local checkout:

```powershell
py -3.12 -m pip install -e .
py -3.12 -m unittest discover -s tests -p test_pie_task_telemetry.py -v
$env:PIE_TASK_ID = "blender-material-001"
$env:PIE_APP = "blender"
pie-usage report --workspace .
```

Restart the Codex/MCP gateway after changing environment variables. Ensure
the gateway is actually selected by Codex; a parallel original MCP
registration can bypass it. The report reads the PIE workspace SQLite
database and shows observed events by app/task/condition.

For a JSON export:

```powershell
pie-usage report --workspace . --output "$env:USERPROFILE\pie-live-evidence\task-usage.json"
```

## Real provider tokens

Use the existing authenticated paired runner described in
`docs/pie-live-certification.md`. It performs 3 baseline and 3 optimized
read-only Codex runs. The scenario must require the intended tool and use
the same model, prompt and correctness oracle. It must be performed for
Blender and web separately. **The runner is not invoked automatically.**

After successful local capture, import each record into the ledger:

```powershell
pie-usage import-codex --workspace . --record "C:\path\optimized-01.json" --app blender --task-id blender-material-001
```

Import both baseline and optimized records with their corresponding
conditions, then inspect the `pie-usage report` totals. The ledger stores
provider-reported tokens, not a cost estimate. The certification result
remains exclusively the output of `pie-live compare`, which enforces
paired comparisons and correctness oracles.

`provider_certified` in the task ledger is always false by design: an
individual usage event cannot certify savings. The paired summary can
report certification for a specific controlled scenario, not globally.

## Costs and privacy

Prices are not inferred from subscriptions. Provide actual per-million-token
input/cached/output tariffs to the existing `pie-live compare --prices`
command for a tariff estimate. Subscription quota usage is not an invoice.

Do not import raw Codex JSONL into the ledger: only sanitized capture
records from `pie.certification.cli capture` are supported. The database
can contain operational metadata and should remain local. Delete or
rotate the database according to your retention policy.

## Acceptance gates

- CI and local tests pass
- Both PIE MCP routes are selected and verified on Windows
- Blender and web each have at least three correct paired baseline/optimized
  runs with real `turn.completed.usage`
- Tool-routing audit confirms expected coverage
- Report shows app/task counts and real tokens separately from characters
- Any missing provider data is reported as missing, not estimated
