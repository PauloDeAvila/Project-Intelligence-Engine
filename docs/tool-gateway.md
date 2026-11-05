# PIE Tool Gateway — Phase 1, explicit MCP routing

The local Tool Gateway is a **single MCP entry point** for supported,
allowlisted operations. It routes the caller's request to PIE code/memory
lookups or the RTK-style output adapter and records a **sanitized** original
in project-local SQLite before returning a bounded result.

## Tool

`pie_tool_gateway` arguments:

```json
{"operation":"task_search","arguments":{"query":"authentication"},"max_chars":4000}
```

Supported read-only operations: `project_status`, `source_query`,
`task_search`, `task_resume`, `context_pack`, `output_get`.
An explicitly supplied log/text can be submitted via `output_compact`.
The gateway cannot execute shell commands, manipulate arbitrary paths,
access web URLs or invoke unknown tool names.

## Bounded response and recovery

The gateway uses compact JSON serialization, saves the sanitized source result
in SQLite and returns the source content when the **complete serialized
gateway envelope** fits `max_chars` (512..64000). If it does not fit,
the gateway reports `state=PARTIAL`, a local `output_id`, and no clipped
claims. Use `output_get` to recover the full sanitized payload, or refine
the original query. Failures propagate as MCP `isError` rather than
masquerading as success. `output_compact` returns RTK-style deduplicated
text, preserving an explicitly supplied exit code.

## What is automatic (and what is not)

Within `pie_tool_gateway`, routing, output capture, redaction and budget
enforcement are automatic. It does **not** transparently hook arbitrary
Codex, Claude, terminal, browser or third-party MCP calls, and it does not
restrict native agent access to tools outside PIE. A client must discover
and invoke `pie_tool_gateway`, or a separately installed and tested
client-specific adapter must route calls through it.

The gateway stores at most 500k sanitized characters per successful
operation. Regex redaction is best effort and NOT a complete secret scanner;
do not pass confidential values. SQLite persistence needs retention/quotas
before unattended high-volume deployment.

`source_chars` is an exact sanitized character count, NOT true model
token use. Whole-task and provider-level cost savings remain unmeasured
pending the separately planned benchmark. Memory entries are
agent-provided unverified claims until source evidence is independently
checked.

## Validation

Run `python -m unittest discover -s tests -p test_pie_tool_gateway.py -v`,
the full unittest suite, and the existing Linux/Windows CI matrix.
No external API, RTK binary, Codex invocation, or model credentials required.
