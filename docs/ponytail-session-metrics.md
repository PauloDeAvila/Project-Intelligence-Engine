# PIE session metrics — Ponytail-inspired, no architecture replacement

Source study: https://github.com/dietrichgebert/ponytail (Ponytail), in
hooks/band/metrics.ts, hooks/band/board.ts and benchmarks/agentic/run.py.

Ponytail records per-task cost, tokens (base input, output, cache reads and
cache writes), time, turns, tests and code reuse. Its benchmark scores real
agent workspaces and can re-score saved outputs without new API calls.

## PIE adaptation

Keep the existing Python token observatory and original PIE retrieval unchanged.
The new `pie.telemetry.session_metrics` module reads existing saved
`results.json` from cloud PIE runs. It never contacts a provider, spins up a
model, captures or prints API keys, modifies source, or counts estimates as
actual API usage.

It reports per-mode attempts, successes/failures, total provider tokens,
cache reads/writes, model latency, known grading/certification, optional
*estimated* cost from explicit rates and cost per certified answer.
Complete pairs are matched by (repeat, case), never cherry-picked across
different tasks or partially failed runs.

Important provider semantics:
- OpenAI-compatible endpoints: `prompt_tokens` includes cached input; do NOT
  add `cached_tokens` again. Reasoning tokens are already accounted for in
  output when reported. If cached detail absent, do not claim zero cached.
- Anthropic: `input_tokens` excludes separate cache-read/write counters; sum
  them for overall usage only when ALL four counters exist.
- Unknown counters stay null. Savings remain null if any successful paired
  observation lacks reported totals. Costs are null unless explicit complete
  model pricing is supplied. Never infer billing from text length.

## Re-score without inference

    PYTHONPATH=src python tools/pie_session_metrics.py benchmark-results/results.json --out benchmark-results/session-metrics.json

Optionally supply all four USD/Mtoken rates:
`--input-per-million`, `--output-per-million`,
`--cache-read-per-million`, `--cache-write-per-million`.

For existing Codex CLI JSONL (turn-level counters only):

    PYTHONPATH=src python tools/pie_session_metrics.py codex-run.jsonl --codex-jsonl --out benchmark-results/codex-session.json

Codex cached-input and reasoning-output counters are already subsets of
input/output. They are not added again. Only counters from turn.completed
are aggregated; no prompts, arguments or model outputs are copied to reports.
Cost and whole-agent wall clock are unknown unless separately supplied by an
authoritative source.

No rates are baked in: models, provider billing, prompt-cache features and
exchange rates differ. No independent proof of model correctness is inferred.
The sample benchmark of two cases remains insufficient for general claims.

## Improvement candidates (not implemented)

1. Persist project-local, append-only session records with immutable run IDs,
   CLI/Codex event provenance and explicit snapshot/watermark deduplication.
   Never reconstruct cache counters by assigning leftovers to input.
2. Collect actual whole-agent turn counts, MCP tool calls, end-to-end wall
   clock and stale-test states; distinguish SDK and Codex token semantics.
3. Test cost-per-certified-success and paired task completion on independent
   cross-repo fixtures, before enabling any retrieval changes.
4. Make any UI dashboard optional; don't mix billing monitoring with
   source-grounded retrieval or introduce a resident agent hook by default.

## Verification

    python -m unittest discover -s tests -v
    python -m compileall -q src tools tests
    python tools/verify_project.py
