# PONTO review — PIE memory/gateway/Blender delta/measurement

Date: 2026-11-14
Branch: feat/pie-memory-gateway-blender-delta-20261114
PR: #64 (stacked atop #63)
Review mode: read-only code-contract and CI evidence review. Not an external human approval.

## Decision

**BLOCKED FOR PRODUCTION MERGE / NOT CERTIFIED FOR BLENDER GUI OR ACTUAL TOKENS.**
The deterministic code slice is reviewable as experimental work only.
Do not merge before live Blender/Codex acceptance and independent review of
provider receipts and quality. Passing CI alone cannot satisfy this contract.

## Scope and source mapping

- src/pie/interfaces/cli.py and src/pie/interfaces/mcp_server.py:
  additive persistent task memory, FTS5 retrieval, output gateway, compact profile;
  verify existing proof Context Packs and Context Mesh tools remain present.
- src/pie/retrieval/task_memory.py and task_search.py: explicit checkpoints,
  transactional event append, project isolation, bounded search.
- src/pie/retrieval/output_pipeline.py: sanitized-output SHA-256 recovery,
  seven-day, 128-row and 8-MB quotas, deduplication, source manifests.
- src/pie/interfaces/tool_gateway.py: operation allowlist and hard-bounded,
  offset-page recovery, source-file manifest collection.
- src/pie/interfaces/setup.py: opt-in compact MCP profile, full defaults.
- src/pie/integrations/blender_mcp_bridge.py: transparent upstream stdio
  pass-through, read-only scene-delta tool, snapshot cache and expansion.
- src/pie/integrations/blender_delta.py: typed read-only bpy snapshot script,
  deterministic fingerprints and scoped incremental diffs.
- tools/certify_pie_blender_three_arm.py: validation of complete, same-task,
  same-scene, same-model and same-sampling comparisons, with independent
  correctness results required.

## Verification matrix

CI: GitHub Actions Validation Gate on Linux and Windows; direct Python
unittest discovery and project verification matrix. Confirm final head
status in GitHub Actions; do not reuse a green result from an earlier
head after a code change. Focused tests:

- test_pie_task_memory.py, test_pie_task_search.py;
- test_pie_output_pipeline.py, test_pie_tool_gateway.py;
- test_pie_memory_recovery_integration.py (separate subprocesses,
  deduplication, TTL/count retention, source drift and pagination);
- test_blender_delta.py, test_blender_delta_stdio.py,
  test_blender_mcp_bridge.py (mock upstream);
- test_pie_compact_profile.py;
- test_pie_blender_three_arm.py (synthetic fixture arithmetic only).

No claim of successful Blender GUI or real Codex token usage has been
verified by this reviewer. The CI mock is not a substitute.

## Findings and residual risk

HIGH — Live Blender addon handshake and execute_blender_code safe-mode
behavior are not run in this CI. Material output fidelity, actual shader
compatibility and visual quality remain unverified.

HIGH — Real paired model tokens are missing. The three-arm assessor
requires externally provided usage receipts; its fixtures are synthetic
test values and must not be publicized as measured savings.

MEDIUM — Delta covers tracked object transforms, binding metadata and
shader-node fields. External texture file contents, mesh topology,
Geometry Nodes side effects, drivers and rendering are not fully
fingerprinted. UNCHANGED is scoped to tracked observation fields only.
Node links are represented by digests in the bounded report.

MEDIUM — Task events are agent-supplied claims; source references may
be stale or wrong. Do not equate task-memory retrieval with a verified
current code state.

MEDIUM — Output redaction is best-effort regex sanitization, not a
secret scanner. Do not submit credentials to the persistent store.
The source manifest protects referenced indexed Python source files,
not unreferenced files or arbitrary external assets.

LOW — The proxy stores scene snapshots only in process memory. Restart
resets comparison baselines; a manual Blender edit is detected on the
next explicit observation, not continuously. This is documented.

## Acceptance gates for closing BLOCKED

1. All GitHub checks green for the exact final head, Linux and Windows.
2. Test with a live supported Blender GUI and corresponding addon
   for scene read, before/after material update, native tool passthrough,
   mixed image responses, errors, undo and session restart.
3. Independent PONTO review compares live scene properties and/or
   images with an independently established ground truth.
4. Collect actual provider-reported tokens for three equally pinned
   conditions, with paired success and latency. Confirm non-degraded
   correctness and target savings before any 85% claim.
5. Document migration, retention consent and rollback when deploying
   to existing user workspaces.

Until then, treat the work as an experimental integration and never
report 100% compatibility or a certified model-token reduction.
