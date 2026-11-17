# Codex isolated MCP executor

Commit `b44d079` integrates the proven temporary Codex home into the
certification controller and CLI.

During an isolated capture, PIE selects the expected MCP server, creates a
temporary `CODEX_HOME`, copies `auth.json` only for the capture, writes a
minimal configuration containing that server, runs Codex with
`--approve-for-me`, and removes the temporary home afterward. The original
Codex configuration is not modified.

Validation: 21 focused live/controller tests and 1 isolation test passed;
the full suite passed with 726 tests, 4 skips and 126 subtests. The PIE index
is `CURRENT` with the workspace root matching the indexed root.

The previous live isolated route probe remains the behavioral reference. A new
official provider-backed A/B pair through the integrated executor is still
pending, so certification remains `NOT_CERTIFIED`.
