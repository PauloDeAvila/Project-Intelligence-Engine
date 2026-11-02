# PIE Context Retrieval Research — 2026-11-02

## Techniques evaluated for adoption

- Aider repository maps: graph ranking over source dependencies under token budget. https://aider.chat/docs/repomap.html
- Contextual Retrieval: contextual BM25, optional embeddings and reranking. Published retrieval miss reductions are not token savings. https://www.anthropic.com/research/contextual-retrieval
- Agent Retrieval Bench: use action-oriented file relevance, no-match cases and regression-test links, not just lexical docstring overlap. https://agent-retrieval-bench.github.io/
- CodeGrep (ACL 2026): retrieval precision is critical to downstream coding agent utility; published 19% token reduction on resolved cases is not a PIE measurement. https://aclanthology.org/2026.realm-1.80/

## Already implemented on this PR

- SQLite-indexed Python AST summaries and source-hash verification.
- Impact analysis expands verified references only, and flags ambiguity.
- SQLite-backed source-verified glossary, incremental polling watcher.
- Adaptive source selection: concise path:line with signatures or source bodies, optionally using shorter full source if indexed-current.
- Automated source scale testing and separate generation/secret-free sandbox verification for code edits.

## Measured comparisons

- Experimental navigation, three repositories, 60 questions: 63.58% total provider-reported input savings (48/60 baseline vs 57/60 compact). Experimental retrieval rather than production PIE.
- Rich 12-task production smart context experiment: ~61.8% savings on paired successful calls; compact 12/12 exact vs baseline 9/12 attempts, of which two API requests failed. Median compact inference 0.985 s.
- 5,000 synthetic files: approximately 0.08 s local context lookup for roughly 198k returned characters; not model inference.
- Four curated code edits, structured PIE context: 1.67% additional input tokens compared with baseline. With adaptive presentation: 2.62% fewer reported input tokens, PIE 3/4 vs conventional 2/4 executable pass. Samples too small for statistical conclusions.

## Next hypotheses and strict gates

1. Prototype SQLite FTS5/BM25 over index descriptions and evaluate recall@K, precision@K, no-match and incremental invalidation against current name/docstring scoring.
2. Explore dependency-centrality ranking only for verified edges; compare the actual downstream coding outcome with an ablation.
3. Optional local semantic embeddings and reranking only if measurable gains offset time and memory costs; offline lexical fallback always.
4. Test larger unseen real-repository edits, multi-file changes, regression suites, and full-agent token/latency budgets including all failed requests.
5. 85% provider-reported prompt token savings and <0.9s end-to-end agent completion are targets, not demonstrated achievements; never extrapolate local lookup speed to model latency.
