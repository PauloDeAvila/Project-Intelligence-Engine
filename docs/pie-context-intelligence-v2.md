# PIE Context Intelligence V2 — implementation and measurement

## Scope

The CLI now offers deterministic responsibility-oriented symbol search, bounded reverse
impact investigation, persistent source-backed glossary and a polling index watcher.
The original exact symbol context remains available through
`pie.retrieval.context.build_context(..., strategy="exact")`; the new smart
entry point is `strategy="smart"`. The CLI `pie context` uses smart retrieval.

The smart ranker is **lexical/AST**, not a language model or guaranteed semantic search.
The local symbol summary database is maintained while indexing and backfilled for old
SQLite indexes on the next index run. It stores a short symbol signature and the
first line of the AST docstring; no language-model inference is needed.

## Windows usage

After installing the local editable package:

```powershell
pie index --root C:\path\to\project
pie context "Which function refreshes the cache?" --root C:\path\to\project
pie context "cache" --include-body --root C:\path\to\project
pie impact "refresh_cache" --depth 2 --root C:\path\to\project
pie remember "cache-contract" "Cache invalidation occurs after update" --source "src/cache.py" --root C:\path\to\project
pie recall "cache" --root C:\path\to\project
pie watch --root C:\path\to\project --interval 5
```

The watcher performs repeated **incremental database updates** but still scans
the source tree to detect changed file hashes. It can be stopped using Ctrl+C.
It is not a native OS filesystem event daemon and will not remain active after
its terminal process exits.

The source-backed glossary has explicit manual entries and automatically
indexed symbol descriptions. If a source hash changes, previously stored manual
knowledge about that source is flagged STALE and its description suppressed
until the user updates it. Automatically indexed symbol descriptions are
refreshed when source indexing runs.

Impact traversal is bounded and follows uniquely verified binding references.
It reports *potential* consumers, not runtime certainty. Ambiguous or dynamic
calls are not fabricated. The optional graph's syntactic CALLS edges remain
unresolved when semantic binding cannot be proven.

## Safety and freshness

- Every selected source snippet is verified against its indexed SHA-256.
- The ranker does not rehash every unselected source at query time; global
  project completeness is only known as of the latest indexing scan.
- Context JSON has a strict maximum serialized character budget.
- Source read failures, hash mismatches and partial budgets are explicit.
- The project glossary is **evidence-backed**, not an autonomous inference of
  architectural decisions. Such decisions require explicit documented sources.
- Python is the supported language. Tree-sitter, SCIP, LSP and MCP are not
  implemented by this change.
- Changes are isolated in a PR, never written directly to main before validation.

## Real measurements and limitations

- 60-file GitHub Actions corpus: median local smart lookup ~0.005 seconds
  after indexing short AST summaries, compared with ~0.105 seconds before
  the summary cache.
- 1000-file synthetic corpus: median ~0.013 seconds for a 12k-character
  response and ~0.040 seconds for ~198k characters returned.
- 5000-file synthetic corpus: median ~0.075–0.079 seconds for a 12k-character
  response and ~0.106–0.108 seconds for ~198k characters returned.
- 5000-file synthetic index: 5.73 seconds cold; 0.995 seconds warm.
- One GPT-4o Mini Rich navigation experiment on the earlier v2 candidate:
  10 valid paired requests had 84,611 baseline vs 32,294 compact reported input
  tokens (~61.83% savings). Compact model-inference median 0.9848 seconds.
  The baseline had two failed HTTP 400 requests. NVIDIA returned HTTP 503
  on all 24 calls. No reliable NVIDIA comparison was possible.
- One synthetic four-edit executable benchmark: 1/4 passing per condition
  and -1.67% *paired* input-token savings. Several API responses did not
  produce parseable model code. The generation/validation harness has been
  hardened, but a new full measurement is required.

**These numbers do not establish 85% total input-token savings or end-to-end
model latency under 0.9 seconds.** Local lookup latency and remote model time
are distinct metrics.

The router previously reported ~2789 input tokens even for a two-character
user prompt. If this apparent fixed contribution is unavoidable for a
given route, the upper bound for token savings on the observed paired GPT
baseline (84,611 tokens over 10 requests) is approximately 67%; 85% requires
removing or amortizing that overhead, or a different baseline/context
distribution. Do not call the variable-content component a total cost saving.

## Tests

```text
python -m unittest discover -s tests -v
python tools/check_install.py
python tools/pie_local_latency.py --root .
python tools/pie_context_scale_lab.py --files 5000 --repeats 5
```

The 9Router benchmarks run only on explicitly dispatched workflows after
the route is configured; avoid spending inference quota on every PR commit.
The editable-code lab separates credential-bearing model generation from
secret-free Docker verification, with no network and a read-only container
filesystem for untrusted candidate code. Fixtures are synthetic; real
unseen bug-fix evaluation remains a separate research milestone.
