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

## Stage-0 acceptance gap

The missing artifact is a deterministic runner that records prompt, model,
parameters, project hash, commit, raw JSONL (sanitized), usage events, MCP tool
status, final answer and independent scoring. This branch adds that runner; it
does not execute model calls automatically.

## Roadmap decision

Stage 1 (progressive retrieval) is intentionally not started until Stage 0
produces raw, reproducible paired runs. The 85% number remains a research target,
not a release claim. Future stages must preserve the existing v2 contract,
`PARTIAL`/`exhaustive=false` semantics and freshness tests.
