# PIE Phase 3 — Web pair comparison

This pair used the deterministic local fixture at `http://127.0.0.1:8766/index.html`, the same
prompt, model, commit and initial page state. Both arms completed exactly
`browser_navigate` followed by `browser_snapshot`; both exact-text and fixture oracles passed.

| Metric | Baseline | Optimized | Difference |
|---|---:|---:|---:|
| input tokens | 66,027 | 66,475 | -0.678510% savings |
| cached input | 56,704 | 56,832 | +128 |
| uncached input | 9,323 | 9,643 | -3.432372% savings |
| output tokens | 305 | 300 | -5 |
| total tokens | 66,332 | 66,775 | -0.667853% savings |
| latency | 11,878.006 ms | 11,681.315 ms | -196.691 ms (-1.655926%) |
| MCP calls | 2 | 2 | 0 |
| oracle | PASS | PASS | — |
| route evidence | VALID | VALID | — |

This pair shows a small negative token result and a small latency improvement. It does not
support an economy claim. Costs remain `null` because no verified tariff was supplied.
