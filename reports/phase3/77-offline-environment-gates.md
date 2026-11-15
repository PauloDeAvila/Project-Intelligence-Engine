# PIE Phase 3 — Offline environment gates

Status: `READY_FOR_MODEL_ONLY_AFTER_REVIEW`.

This phase made no Codex/model calls and consumed no quota. It validates the exact MCP commands generated for isolated profiles, with a stable Python executable and the PIE source directory pinned to the experimental commit.

## Four profile probes

| Profile | Server | initialize | tools/list | tools/call | Fixture evidence | Compaction |
|---|---|---|---|---|---|---|
| Blender baseline | `blender` | PASS | PASS | PASS | `PIE_Large_Cube_00` | passthrough; structured content |
| Blender optimized | `pie-blender-optimized` | PASS | PASS | PASS | `PIE_Large_Cube_00` | not applied because upstream returned `structuredContent` |
| Web baseline | `playwright-baseline` | PASS | PASS | PASS | `Products` via `browser_snapshot` | `PASSTHROUGH`, 9,055 chars |
| Web optimized | `pie-web-optimized` | PASS | PASS | PASS | `Products` via `browser_snapshot` | `PARTIAL`, 8,965 → 1,003 chars |

All four profiles contained exactly one domain server. Blender profiles contained no Web server; Web profiles contained no Blender server. The optimized profiles used the stable interpreter from the main checkout and `PYTHONPATH` pointing to the worktree `src`. The verifier confirmed that `import pie` resolved below that source root and that its Git HEAD matched `fbe3f9959d8f7c5bca03879c86139f791ca13f30`.

The Blender fixture was loaded in a separate disposable Blender 5.3 process on port 9877. The real `get_scene_info` response contained `PIE_Large_Cube_00`. It also contained `structuredContent`, so the current bridge deliberately bypassed compaction; this is an important observation for the later A/B design, not a fabricated compaction result.

## Analysis of the invalid 231,599-token session

For `optimized-9823d9e4cfbe6d7413f965f0`, the forensic JSONL contains 6 event lines: 1 `turn.started`, 1 `turn.completed`, 1 agent-message event, 2 error item events, and no MCP tool events. Stderr contains 6 sanitized MCP startup-failure lines. Provider usage is available for exactly one completed turn:

| Metric | Tokens |
|---|---:|
| Input | 230,071 |
| Cached input | 178,176 |
| Uncached input | 51,895 |
| Output | 1,528 |
| Reasoning output | 1,103 |
| Total input + output | 231,599 |

The records do not contain a raw context breakdown, so they cannot prove how many tokens came from initialization, diagnostics, planning, or static tool descriptions. Those remain hypotheses. No tokens are attributed to tools because `mcp_tool_events=0`.

The immediate root cause is proven: the MCP `command` pointed to a nonexistent `.venv\\Scripts\\python.exe` inside the temporary worktree. The new preflight rejects missing commands and mismatched PIE source commits before a model can start.

## Reproduction

The four probes use [verify_phase3_mcp_profiles.py](../../tools/verify_phase3_mcp_profiles.py) with the generated TOML profiles. The Blender fixture is launched separately with [start_phase3_blender_fixture.py](../../tools/start_phase3_blender_fixture.py); the Web probe uses `fixtures/phase3/web/large.html` over a local HTTP server.

No A/B benchmark is released by this report. The objective gate for a new paid run is: all four probes pass, the Codex profile preflight reports the same executable/source/commit checks, and a fresh run records nonzero MCP route evidence before any pair is accepted.
