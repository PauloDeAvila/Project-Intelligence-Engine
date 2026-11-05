# PIE Minimal Sufficient Context — isolated GPT-4o mini A/B

Hypothesis: fewer complete, hash-verified AST evidence snippets may reduce model
prompt tokens while preserving the independent field-level correctness grade.

Modes:
- `pie_rtk` is byte-for-byte the current `compact_source_evidence` serializer over
  the existing `build_causal_context` output.
- `pie_minimal` uses the **same upstream retrieval** and formatter; retains
  every indexed definition, at most the first 3 ranked functions and 1 ranked
  behavioral test. Drops complete less-ranked snippets, never truncates a
  function or fabricates a causal edge. No access to gold, answers or source
  path allowlists during selection.

Caveat: `build_causal_context` itself ranks evidence; that order may not be
sufficient to select the minimally sufficient subset for every task.
Missing facts may reduce quality, so this is an experiment, not default.

Four calls (MAX_RETRIES and release, both modes), exactly one repetition,
randomized order, same system prompt/JSON schema/provider, no retries,
10-second cooldown. Real provider reported usage must be complete or savings
remain unknown. Independent executable post-mutation gold validates fixture;
LLM quality scored separately (4 fields per task). No certification claims.

Commands (offline, no key): `PYTHONPATH=src python tools/benchmark_minimal_context.py --dry-run`
Run on the dedicated GitHub Actions workflow after CI, via a marker-only push
or deliberate workflow dispatch. GitHub-hosted runners need a reachable active
HTTPS 9Router tunnel. Never commit or print endpoint credentials.

Acceptance: valid current source, minimal payload strictly smaller, 4/4 API
requests and complete reported usage; nondegraded correctness and meaningful
paired token savings required before any promotion. Main branch remains
unchanged. Sources, graph, MCP, warm context and gateway are untouched.

## Native 9Router fallback combo

The requested model is now `Leve`, the locally configured 9Router combo.
A non-inference `/v1/models` preflight must return HTTP 200 before any model
call. The existing Cloudflare tunnel URL is temporary; `404` from a stale
tunnel is a transport failure, not evidence of a model failure. Keep the
hard cap of four requests and no retries. Actual-model names reported by
the provider must match across both variants; an unknown or differing model
makes the token-savings comparison **incomparable**. A combo name returned as
`model` may not identify the underlying backend, so treat it as provider-
reported identity, not independently verified backend provenance.
