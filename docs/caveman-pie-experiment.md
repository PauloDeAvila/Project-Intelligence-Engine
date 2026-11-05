# Caveman ideas evaluated against PIE

Sources: https://github.com/JuliusBrussee/caveman

- The Caveman **skill** changes agent writing style, not input context.
- The separate Go Engine compresses tool outputs (including JUnit, pytest/Jest),
  structured JSON/TOON, code and terminal history with explicit recovery,
  safety and source evidence. PIE already has FTS5, hash-verified Context Packs,
  RTK-style output deduplication, and recoverable Tool Gateway.
- Do not introduce another reverse proxy or duplicate FTS5.
- Pixel-based prompts and aggressive AST pruning remain unsuitable for certified
  code-navigation without model- and task-specific fidelity evidence.
- One promising isolated experiment is task-aware test-report compression.

## Opt-in experiment

`tools/caveman_testreport_adapter.py` understands only complete *successful*
Python unittest `-v` output with all individual tests and one summary. It
keeps the exact names of all tests, drops repeated wrapper/header syntax,
and emits a concise success line **only when smaller**. Failure logs, traces,
skipped cases and unfamiliar formats pass through unchanged; no unverified
success or missing failure is introduced.

Benchmark adds two opt-in modes to existing PIE mini-order lab:
`pie_test_generic` = current PIE source evidence + existing RTK-style
generic line-deduped tool output;
`pie_test_structured` = identical source evidence + structured unittest
report. Input is **actual, passing unittest output**, not a fabricated
provider response. The source code and grading are unchanged, so only
test-log representation differs. Both append the same report provenance.

Exactly 2 questions (MAX_RETRIES and release) x 2 modes x 1 repeat = 4
GPT-4o mini requests via existing 9Router secret on GitHub Actions.
No retries, cooldown 10 seconds, max-calls hard cap 4, dry-run first.

Report measured prompt/output/total usage, grading and latency. Test report
context is small relative to source and can *increase* tokens; do not assume
positive savings. Results only apply to this synthetic fixture. There is no
claim of task-level certified quality if only partial fields pass.

Workflow: `.github/workflows/pie-caveman-mini.yml`. Push auto-trigger is
restricted to changes to `benchmarks/trigger-caveman-mini.txt` on the
experimental branch; subsequent code pushes do not silently spend more calls.
Workflow may also be run manually. The Cloudflare tunnel and model entitlement
must still be active. This PR is draft; no main merge.
