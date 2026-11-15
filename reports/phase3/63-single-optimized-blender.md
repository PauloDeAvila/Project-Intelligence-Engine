# PIE Phase 3 — Optimized Blender single run

Status: `OPTIMIZED_BLENDER_FAILED` for certification, with quota consumed and no retry.

The Codex session did execute the optimized route and completed the expected tools:

- run_id: `optimized-fa59ea6b612a471391cd5f34`
- pair_id: `pair-deda0256ba284175ade5d58d`
- model: `gpt-5.6-luna`
- commit: `a95760a9ca0ef53088ae6b2375d9b9571fd3a12b`
- route server observed in Codex MCP events: `pie-blender-optimized`
- tools: `get_scene_info`, `execute_blender_code`, both `completed`
- provider usage: available
- oracle: exact textual oracle passed; independent live Blender read also matched roughness `0.3499999940395355` and metallic `0.20000000298023224`

Provider usage:

| Metric | Value |
|---|---:|
| input_tokens | 76,792 |
| cached_input_tokens | 62,336 |
| uncached_input_tokens | 14,456 |
| output_tokens | 855 |
| reasoning_output_tokens | 334 |
| total_tokens (`input + output`) | 77,647 |
| duration_ms | 22,418.533 |
| MCP calls | 2 |

Certification was blocked because the persisted gateway lifecycle log contained no exact
`run_id`/`pair_id` optimized gateway event. The Codex forensic `mcp-tool-events.jsonl` proves
that the configured optimized server and expected tools were dispatched, but it is not treated
as a substitute for the gateway-owned lifecycle evidence. The run is therefore not counted as
a valid optimized certification arm.

Evidence:

- result: `reports/phase3/63-single-optimized-blender-result.json`
- ledger: `reports/phase3/63-single-optimized-blender-result-budget-ledger.json`
- forensic directory: `C:\Users\phsra\AppData\Local\Temp\.pie-phase3-single-blender-fixed-d23a211ad98c4f7cb2bafc0f7006882c-pie-live-store\runs\optimized-fa59ea6b612a471391cd5f34`
- preflight: `reports/phase3/63-optimized-preflight.json`
