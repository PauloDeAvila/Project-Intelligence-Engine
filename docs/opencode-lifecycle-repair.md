# OpenCode lifecycle repair — PR #39

The previous remote end-to-end test is **FAILED / NOT CERTIFIED**. A task
stuck in RUNNING without a session ID, result or metrics cannot be treated as
a successful PIE evaluation. The earlier Doctor Mesh MCP observation does
not prove that the PIE project was queried.

## Defects addressed

1. `POST /session/:id/prompt_async` returns **204 with no JSON body**. The
   previous adapter assumed all responses were dictionaries.
2. `GET /session/:id` returns metadata, not the authoritative execution
   status. Poll `GET /session/status` and require a terminal assistant
   message from `GET /session/:id/message` before reporting completion.
3. Persist session ID in SQLite **immediately after creation**, before
   prompt submission, via a callback and `session_bound` event. Abort
   requests can then locate the session during processing.
4. Use `X-OpenCode-Directory` with a percent-encoded **allowlisted local
   root** for creation, prompt, status and messages, and verify the session
   reports that root. The JSON body `directory` is not a supported
   reliable selector on affected OpenCode versions. This prevents accidental
   reuse of the Doctor Mesh project when a PIE task is requested.
5. Deny built-in shell, editing, web and sub-agent tools in the per-prompt
   payload. This is a defense-in-depth request to OpenCode, **not** proof
   of host-level sandboxing; plugin/MCP tools need independent verification.
6. Return only assistant-message metadata and reported token counters; do
   not send source text or raw MCP output back through the public gateway.

## Required Windows acceptance test — not executed remotely

- Rotate the publicly disclosed gateway Bearer, restart the gateway with
  the new secret, revoke the previous one, require Cloudflare Access for
  permanent exposure.
- Confirm the configured `projects[id=pie].root` is the actual PIE repository
  and the same root is reported by the new OpenCode session.
- Confirm `GET /mcp` in the same project instance identifies the PIE MCP
  server as connected. The Doctor Mesh MCP does not satisfy this.
- Create one **authorized, fixed read-only** task after checking OpenCode
  model permissions locally.
- Observe `session_bound` while RUNNING, subsequent VERIFIED assistant
  message, and final COMPLETED status with the same session ID.
- Verify the PIE response against current PIE index status and hash-backed
  evidence (never certify merely because a model states CURRENT).
- Verify failed/timeout/cancelled tasks never produce COMPLETED.
- Verify token counters are nullable if the provider does not report them.
- Independently inspect logs and attest tool deny rules (including MCP
  write-capable tools), then run full suite + Pyright on Windows and Linux.

No old stuck task is retroactively marked COMPLETED. It must be cancelled
or blocked/recovered and replaced by a new authorized task.

## Status

Local code and regression tests prepared; **no live end-to-end validation**
or verified connected PIE MCP has been executed by this GitHub connector.
PR remains draft; do not merge without the above.
