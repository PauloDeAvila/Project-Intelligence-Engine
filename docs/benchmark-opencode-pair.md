# Paired Nemotron / PIE benchmark — experimental

The repository contains a separate v2 integration E2E report, but that
**does not measure savings**. This experiment compares matched questions,
same repository and model, two different OpenCode 2.2.x localhost services.

The benchmark records ACTUAL counts when the provider reports them.
No fixed token saving is assumed. Reasoning tokens may already be
included in output tokens and are not double-counted.

## Isolation and controls

- WITH_PIE runs on 127.0.0.1:4097 with mcp.servers.pie enabled.
- WITHOUT_PIE runs on 127.0.0.1:4098 with no PIE server.
- Both use the same model ID and identical native permission rules.
- Every question creates a **new session** in each instance.
- Run sequentially, not concurrently. Baseline first, treatment second.
- Avoid leaking global/project MCPs: OpenCode may merge configurations;
  review effective setup. The benchmark **fails closed** when baseline
  still exposes an MCP named `pie`.
- Baseline is instructed to use read-only native tools, NOT PIE;
  treatment is instructed to use the PIE MCP for evidence.
- A successful treatment must include a completed PIE tool-call record
  and a final successful session idle; baseline must not use PIE.
- Gold answers come from an independently authored fixture:
  `benchmarks/opencode-pair-questions.json`. They are not included
  in model prompts. The fixture is only four simple smoke questions;
  it is NOT a scientific accuracy certification or a representative
  real-world workload.

## Run once (Windows PowerShell; **no Cloudflare**)

Use the isolated PR #39 checkout and ensure `opencode --version`
reports the installed 2.2.5 and the exact Nemotron ID is available.
A Python environment with PIE installed must already exist.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_pie_pair_windows.ps1 -PieRoot "$((Resolve-Path .).Path)"
```

The launcher generates separate configurations, selects an OpenCode
application executable, starts two independent loopback servers,
uses separate random passwords, compares four fixed questions, saves
the JSON file in a fresh private directory under
`%LOCALAPPDATA%\pie-bench-<UUID>\results.json`, then stops only
its own servers. The output path is printed. The original OpenCode
and the public PIE gateway are not modified.

Never use the publicly disclosed bearer token to run this experiment.

## Result semantics

`tools/benchmark_opencode_pair.py` stores session IDs, tool proof
hashes, per-question correctness (exact short answer compared with
independent gold), latency, provider-reported input and output tokens.
No raw private MCP/tool transcript or entire source file is saved.
Errors, timeouts and missing metrics stay explicit.

`token_savings_pct = 100 × (without_tokens - with_tokens) /
without_tokens` only for pairs with valid integer input **and** output
token counts on both sides. Summary includes exact denominator
`token_comparable_pairs`. `certified=false` if any pair is missing
complete metrics. A successful outcome can be negative savings;
never clamp it to zero.

This smoke experiment must be expanded with independent, multi-repo,
nontrivial question fixtures and repeats before claiming that PIE
saves >=85% tokens or improves answer correctness generally.

## Release gate

Do not merge PR #39 or re-enable the public tunnel before reviewing
the runtime logs, checking that both servers truly used the same
Nemotron backend and effective model settings, and rotating the old
public gateway bearer. The E2E evidence JSON refers to an earlier
commit ID and requires an independent replay for release certification.
