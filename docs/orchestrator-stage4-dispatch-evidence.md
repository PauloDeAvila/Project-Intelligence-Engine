# Stage 4: dispatch queue and PIE MCP evidence

This is an **experimental** implementation on PR #39; DO NOT MERGE
or restart a public gateway until all acceptance checks pass.

## Opt-in dispatch

`POST /v1/tasks` and mapped GitLab webhooks persist a task and wake a
single gateway worker **only when** `"auto_execute": true` is set in
the locally private configuration. The default remains `false`, so
exposing a previously configured gateway never silently starts agents.
The worker uses an independent SQLite connection (not the HTTP handler's
connection), processes pending tasks sequentially, and resumes pending
tasks after process restart. Pre-existing RUNNING tasks are NOT
retroactively certified: the prior startup recovery marks them BLOCKED.
A second concurrent gateway instance sharing the same database is not
supported and must not be deployed.

## Evidence requirement

The OpenCode adapter now requires both a completed assistant response and
at least one **actual completed PIE MCP tool event** from the OpenCode
message parts. User/assistant text claiming `CURRENT` is not evidence.
Doctor Mesh tool invocations are not evidence of PIE.

The result includes `pie_mcp_evidence` entries consisting of tool name,
call ID, completion state, SHA-256 of the raw tool output and its byte
length. The tool's raw output is NOT copied into the public gateway
result; retain the OpenCode session/message history locally to independently
compare the hash. `index_validation` contains separately captured
local PIE CLI index/freshness metadata. Provider token metrics are
nullable and must not be synthesized.

The hash proves only the integrity of the observed tool response for later
audit, not that its contents are correct or that the agent fully answered
the question. Certification still requires an independent comparison to
the actual PIE project index. This is a constrained one-task read-only
MVP, not a permission-isolated general-purpose remote code executor.

## Acceptance criteria (not yet run here)

1. **Rotate the publicly disclosed gateway Bearer FIRST**. Restart
   gateway under a new, random secret; revoke the old token and verify
   it fails. Configure Cloudflare Access before stable public deployment.
2. Review OpenCode MCP connection for actual PIE (not Doctor Mesh);
   keep workspace root allowlisted and host/tool permissions restricted.
3. With `auto_execute=false`, submit one test task to a LOCAL
   gateway and confirm it stays PENDING without an inference call.
4. Run full tests and Pyright on Windows and Linux.
5. In the locally controlled environment only, change to
   `auto_execute=true`, restart with rotated token and submit one
   allowed task. Verify `session_bound` during RUNNING, actual PIE
   tool-call record and output hash, then COMPLETED, matching session
   and expected model.
6. Verify no PIE tool call, tool failure, timeout or wrong MCP does
   **not** reach COMPLETED.
7. Preserve the older stuck task as FAILED/BLOCKED for historical
   reporting; never count it as a successful execution.

A real Cloudflare/Windows/OpenCode test cannot be claimed from the
GitHub PR alone. Neither the disclosed Bearer nor other secrets have
been used here.
