# PIE RTK-style Tool Output Standard — experimental

This is a Python implementation inspired by RTK's design, **not** a copy,
installation, invocation or complete replacement of the external RTK binary.

## What is implemented

- `pie output-compact --file run.log --kind test --root <project>`
- `pie output-get --output-id <opaque-id> --root <project>`
- MCP `pie_output_compact` / `pie_output_get`.
- Deduplicates repeated exact lines; prioritizes failure lines on tests/logs;
  preserves an explicitly supplied exit status.
- Explicit `PARTIAL` state and omitted-line count if output exceeds a budget.
- Project-local SQLite storage of the **sanitized original**, SHA-256 checked
  when retrieved, with opaque IDs; project isolation applies.
- Common ANSI and credential patterns are removed **before storage**. This is
  a best-effort pattern filter, not a guaranteed secret scanner. Avoid input
  containing secrets whenever possible. Never persist the pre-redaction raw
  text. External log content is untrusted.
- Every PIE MCP tool response uses JSON compact separators automatically,
  preserving the original structured keys/values; this is not semantic
  compression and may provide only small reductions.

## Example

```powershell
pie output-compact --file "test-run.log" --kind test --exit-code 1 --root "C:\\MyProject"
pie output-get --output-id "<returned-id>" --root "C:\\MyProject"
```

Unlike `rtk init --global`, the current integration **does not hook or
intercept all shell commands/agent tool calls**. The CLI/MCP adapter must be
called by a compatible workflow, and external tools such as Codex/Claude
require separate verified client-specific hooks if automatic interception
is desired. Use RTK itself where its official integration is supported; do
not stack double-filtering hooks.

The `source_chars`/`returned_chars` fields measure sanitized Unicode
characters, **not native-model tokens**, provider billing or whole-task
savings. Token Observatory from PR #28 is a separate feature and is not
silently merged into this stacked branch.

## Validation

`python -m unittest discover -s tests -p test_pie_output_pipeline.py -v`;
then the full unit suite and Windows/Linux 6-tier CI verification.
Failure exit codes remain reported. A partial output must be recovered
before using it to assert the absence of warnings or other evidence.
