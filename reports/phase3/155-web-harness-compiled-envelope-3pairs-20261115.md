# Web local harness — compiled envelope, three pairs

The Context Runtime was changed to retain only a minimal typed envelope around
the semantic `preview`, instead of forwarding the complete gateway metadata.
The answer instruction remained explicit enough to preserve correctness.

| Metric | Baseline | Optimized |
|---|---:|---:|
| Total tokens, 3 pairs | 8,093 | 478 |
| Input tokens, aggregate | 8,000 | 351 |
| Output tokens, aggregate | 93 | 127 |
| Total savings | — | **94.094%** |
| Correctness | 3/3 | 3/3 |

All six arm oracles passed, the order alternated, and no Codex session or paid
Codex quota was used. This remains a deterministic replay against the local
OpenAI-compatible harness using `gambiarraapi/glm-5.3-flash`, not Codex
certification.

The preceding bare-preview experiment passed one oracle but increased hidden
reasoning and achieved only 87.537%; it is preserved as evidence and was not
promoted. A minimal answer instruction caused an oracle failure and was closed
without counting savings; see report 156.

