# Cloud PIE benchmark: methodology and acceptance gates

## What it compares

All modes use the same 9Router model, system prompt, synthetic Python project, tasks and output schema:

1. `baseline`: all project files.
2. `pie_raw`: original indexed retrieval JSON.
3. `pie_auto`: AST-based automatic causal retrieval JSON.
4. `pie_compact`: **exactly the same automatic causal evidence**, serialized with path/line provenance but without redundant JSON fields.
5. `curated_reference`: manually chosen source snippets for each question. **Oracle reference only**, never counted as an automatic PIE improvement.

Three known-behavior change-impact questions: `MAX_RETRIES`, `release`, `charge_with_retry`.

## Quality is a hard constraint

The benchmark asks for an explicit JSON response with four independently verifiable facts for each scenario. A deterministic grader compares each fact with the known behavior of the laboratory. It scores malformed or absent fields as incorrect, retaining the raw response.

The code fixture is run against its real Python `unittest` suite before inference. The retrieval audit fails closed if the required code or tests are absent, before spending API calls. This laboratory's predefined facts are not a substitute for human review of real-world codebases.

## Performance

Record prompt/completion/total tokens, response latency, model ID, finish reason, context hash and length, one-time indexing time and retrieval time. Provider-side token overhead may dominate small prompts; use **paired per-case comparisons** rather than aggregate medians alone.

For latency use multiple randomized repetitions and report median paired delta and spread. Index cost is amortized across queries; also report cold-start economics. Quality must not regress before claiming speedup.

## Valid conclusion criteria

- Both modes have fully valid responses (`finish_reason=stop` and all 4 facts correct), with multiple repetitions.
- Automatic PIE uses fewer **measured prompt tokens** and delivers lower **end-to-end query latency**, including retrieval, for a pre-indexed project.
- No unsupported assumption that fewer characters implies fewer billed tokens.
- Evaluate on larger, realistic open-source codebases with independent change-impact questions before claiming broad generalization.

## Known limitations

- Name-based AST call expansion is not full data-flow, dispatch or exception-effect analysis.
- Small synthetic project; complete baseline fits in context.
- `curated_reference` is an upper bound using question-specific source lists and is excluded from claims.
- 9Router model routing and performance vary by provider, quotas and load.
- Cloudflare Quick Tunnel can expire/change URL; GitHub-hosted runners need a reachable HTTPS endpoint.
- No automatic merge to `main`; PR and CI gates apply.

## Safety

Never commit API tokens, passwords or tunnel credentials. Use GitHub repository secrets; do not print raw request headers. The previously disclosed key and tunnel password should be rotated.

