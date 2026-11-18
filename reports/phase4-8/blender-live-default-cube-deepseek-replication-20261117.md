# Blender live default-cube replication — DeepSeek 3.2

Status: `CERTIFIED` by the local replication gate; this is not Codex certification.

Evidence:

- Three paired live runs, same default Blender scene, task oracle and model.
- Provider: `gambiarraapi/deepseek-v3.2` through the local Infinity endpoint.
- Baseline and optimized oracles: 3/3 each; all six arms passed.
- MCP calls: 3 per arm in every pair; no automatic retries.
- Baseline total: 15,603 tokens; optimized total: 738 tokens.
- Total savings: 95.27014%.
- Uncached input baseline: 5,191; optimized: 153; savings: 97.052591%.
- Mean provider latency: baseline 4.2566 s; optimized 2.391733 s.

The first pair was cold-cache (`baseline_cached_input_tokens=0`); pairs 2 and 3
reported cached input on both arms. The total-token result remained identical
across all three pairs, so cache state is recorded rather than hidden.

Machine-readable gate: `blender-live-default-cube-deepseek-replication-gate-20261117.json`.

This evidence certifies the local provider/fixture replication only. It does not
replace the pending official Codex A/B certification or broader Blender/Web coverage.
