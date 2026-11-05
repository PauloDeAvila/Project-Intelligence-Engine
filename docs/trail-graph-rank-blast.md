# Trail-Code-inspired improvements: verified PPR + diff blast

Reference (MIT): https://github.com/trailhq/Trail-Code, notably
src/ask/graphrank.ts and src/blast/blast.ts. This is an independent Python
adaptation of the *algorithms*, not a copy of the TypeScript implementation.

## Features

- **graph-rank**: calls the existing PIE FTS5/AST lexical retrieval to produce a
  bounded candidate pool, constructs a personalized PageRank walk over only
  verified binding references in the already-indexed graph, and reranks the
  results. Scores are heuristic and not certified dependency evidence.
- **blast-diff**: safely obtains the unrenamed Git diff against HEAD, maps
  changed new-side line ranges to the smallest indexed symbol spans, and
  traverses only verified reverse binding edges to identify *potential*
  consumers. Deleted/untracked files are not included as covered symbols.
- Both refuse stale full-source graph snapshots, operate locally, and have
  bounded JSON outputs. No network, provider token usage or LLM dependency.
- CLI: pie graph-rank QUERY --root ROOT; pie blast-diff --root ROOT.
- MCP: pie_graph_rank and pie_blast_diff. The default pie_query behavior is
  not silently changed: callers can compare variants deliberately.

## Offline A/B benchmark

Run:

    python tools/benchmark_trail_pie.py --repeats 5 --out benchmark-results/trail-inspired.json

Measures lexical vs PPR rank on identical queries, plus a coarse file-level
impact estimate vs diff-symbol-level verified potential consumers. The
synthetic fixture has an executable ground truth for changed symbols.
The output contains hit-at-3, median wall-clock latency, impacted consumer
counts, and zero external inference calls. This measures local algorithms,
**not** model tokens, end-to-end correctness, or NVIDIA API speedup.

## Gaps / safeguards

PageRank does not prove a call relationship. Unresolved dynamic dispatch
must not be promoted to verified. Strict full-project source verification
adds latency on large repos; measure before enabling by default. Diff is
computed relative to HEAD and does not cover untracked files or change
content that is absent from the current index. No hidden code modification
and no automatic merges.
