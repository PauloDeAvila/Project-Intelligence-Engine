# Web local harness — preview-only compiled envelope, three pairs

The compiled context now sends only a typed JSON object containing the semantic
`preview`. The gateway's full metadata remains available to the local runtime,
but is not forwarded to the answer model.

| Metric | Baseline | Optimized |
|---|---:|---:|
| Total tokens, 3 pairs | 8,094 | 476 |
| Input tokens, aggregate | 8,001 | 321 |
| Output tokens, aggregate | 93 | 155 |
| Total savings | — | **94.119%** |
| Correctness | 3/3 | 3/3 |

All six arm oracles passed and the baseline/optimized order alternated. This is
local-provider replay evidence using `gambiarraapi/glm-5.3-flash`, not Codex
certification. The 95% target remains unreached.

