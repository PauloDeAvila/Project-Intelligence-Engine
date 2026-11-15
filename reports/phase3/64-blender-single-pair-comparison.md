# PIE Phase 3 — Blender pair comparison

This is one real paired attempt, not a certification result. Both sessions used the same
scenario, prompt hash, model, effort, workspace commit, and initial Blender state. The
optimized call consumed one authorized session and was not retried.

| Metric | Baseline | Optimized | Difference |
|---|---:|---:|---:|
| input tokens | 58,889 | 76,792 | -30.40% savings |
| cached input | 35,840 | 62,336 | +26,496 |
| uncached input | 23,049 | 14,456 | 37.28% savings |
| output tokens | 685 | 855 | +170 |
| total tokens | 59,574 | 77,647 | -30.34% savings |
| latency | 17,451.210 ms | 22,418.533 ms | +4,967.323 ms (+28.46%) |
| MCP calls | 2 | 2 | 0 |
| oracle | PASS | PASS | — |
| route evidence | VALID | INSUFFICIENT_EVIDENCE | — |

The optimized arm reduced uncached input but increased total provider-reported tokens and
latency. This is an unfavorable result, not a reason to discard data. Cost remains `null`
because no verified tariff was supplied.

The pair cannot be counted toward certification because the gateway-owned lifecycle evidence
for the optimized route did not contain an exact `run_id`/`pair_id` match. Codex forensic MCP
events do show `pie-blender-optimized` and both expected tools completed; coverage is therefore
partial, not certified gateway correlation.
