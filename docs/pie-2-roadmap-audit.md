# PIE 2.0 roadmap audit — `main` 7dd2ff6

## Current evidence

- The `main` suite passes 324 tests with 2 platform skips.
- Context Pack v2, qualified methods, partial coverage and fail-closed freshness
  are implemented and covered by unit, integration and MCP tests.
- Doctor Mesh snapshot artifacts are versioned for five repetitions and carry a
  snapshot hash.
- The repository records a Codex token summary for five repetitions per mode,
  but not the raw JSONL runs. The 45.1% and 31.3% figures are therefore
  repository-reported measurements, not independently re-runnable from `main`.
- The repository does not contain the raw persistent-MCP run proving 1.466 s to
  0.827 s. That latency claim must remain experimental until its raw paired
  artifact is published.

## Stage-0 hardening result

The paired runner now records prompt hashes and sanitized prompt files, the
requested/effective model source, the scanner-produced project inventory,
snapshot hash, raw and sanitized JSONL hashes, usage events, MCP tool status and
an independent structured gold score. The no-PIE command uses
`--ignore-user-config`; the PIE command keeps the configured MCP servers. A
post-run scanner manifest comparison fails the benchmark if the project changes.

The five-repetition artifact is `benchmarks/results/stage0-final-v4.json`.
It contains ten successful Codex sessions on the same 45-file snapshot:
all five direct runs have no PIE MCP calls and all five PIE runs execute
`pie-doctor-mesh`; all ten structured definition/caller scores pass. The CLI
could not accept the desktop-only `ag/claude-opus-4-6-thinking` identifier with
a ChatGPT account, so the artifact explicitly labels the effective source as
`codex-config-default` rather than claiming an unsupported model override.

## Roadmap decision

Stage 1 (progressive retrieval) is intentionally not started until Stage 0
produces raw, reproducible paired runs. The 85% number remains a research target,
not a release claim. Future stages must preserve the existing v2 contract,
`PARTIAL`/`exhaustive=false` semantics and freshness tests.
