# PIE + RTK: token-saving adapter (experimental)

RTK source: https://github.com/rtk-ai/rtk . Concepts used: filter noisy tool output, group repeated log lines, deduplicate and budget outputs, provide structure-first file browsing. This code was independently written in Python; no RTK source code or licensed compression engine is embedded.

The integration does **not** claim that the RTK Rust binary runs inside PIE Python. RTK filters *tool/command output*, whereas PIE retrieves *source evidence*. Apply RTK or the independent adapter to test logs, Git diffs and diagnostics; apply the PIE adapter to already-selected code. Preserve exact source lines and references whenever assessing behavior.

Module `tools/rtk_style_context.py` provides:
- `compress_tool_output`: deduplicates repeated lines, prioritizes failure lines, marks partial outputs and masks common secrets.
- `python_outline`: AST structural inventory as a navigation aid, **not a substitute for source**.
- `compact_source_evidence`: deduplicates source ranges, removes redundant JSON metadata, preserves full source code and path/line provenance. Stale context is rejected; partial context is labeled.

Caveats: regular-expression credential masking is defense-in-depth, not a replacement for proper secret-handling. Failure-first log compression can omit a necessary non-error precursor if the budget is exceeded; retrieve complete logs if the result is PARTIAL. RTK's bytes/4 estimated token metric is not equivalent to provider-reported prompt tokens. Do not claim savings until verified with actual model usage and stable semantic grading.

Doctor Mesh attachment was studied separately as an offline workload. Its binary assets and user source code have **not** been committed to this public repository.
