# PIE DES-04 — static traceability and frozen real-repository evaluation

**Status: experimental foundation; not a scored real-repository benchmark.**

DES-03 established strong schema-constrained field selection in an intentionally
narrow corpus. DES-04 must evaluate source-backed relationships across files
without confusing graph topology with causal impact.

## Certified vs possible vs unknown

- `verified_static_direct_call`: a resolved syntactic call in the indexed,
  hash-verified local Python snapshot. The report contains consumer file/line,
  target binding/file/line, evidence ID, target SHA and resolution label.
- `POSSIBLE_UNVERIFIED`: a hypothesis for separate investigation, **not** a
  certified graph edge. This initial foundation deliberately emits no possible
  edges until a bounded and separately tested discovery rule exists.
- `UNDETERMINED`: runtime behavior, compatibility, and whether changing the
  function will break other components. Direct calls alone never certify this.
- `ABSTAIN`: stale/incomplete index, ambiguous symbol, unresolved evidence,
  or questions exceeding static proof coverage.

The new `pie.retrieval.static_traceability.inspect_static_dependencies`
uses the existing strict evidence engine. It does not claim indirect call
closure, dynamic dispatch coverage, or runtime breakage. This is a Python
function only; **no new public Gateway endpoint has yet been added**.

## Real-repository benchmark must be frozen BEFORE Qwen evaluation

Candidate projects:
- [psf/requests](https://github.com/psf/requests)
- [pallets/click](https://github.com/pallets/click)

These are **candidates**, not pinned or independently reviewed test sets.
The file `evaluation/des04/manifest.draft.json` intentionally contains null
commit SHAs and zero evaluated questions. The published draft cannot pass the
freeze validator. Do not convert this to a claimed real-repo experiment.

For each real repository:

1. Verify repository permission/license and choose an exact, permanent full
   40-character Git commit SHA (never a moving `main` branch).
2. Create a *clean, isolated clone*, confirm `git status --porcelain` is empty,
   and record both the repository URL and resolved SHA.
3. Index a read-only copy in PIE. Record any `PARTIAL`, `STALE` or
   `ERROR` results; do not silently repair test failures.
4. Draft at least eight questions per repo, covering:
   verified direct call, duplicate/ambiguous names, multi-file evidence,
   indirect/dynamic unresolved dispatch, modified source, newly added
   unindexed source, unresolved reference and insufficient evidence for
   causal breakage.
5. Have **two independent reviewers** examine exact source spans, ambiguity,
   expected static relationship and limitations. Record their review IDs.
6. Freeze the complete question/gold manifest (all cases contain
   `case_id`, `repository`, `question`, `category`, `expected_status`,
   `expected_breakage:false`, `source_spans`, `reviewers`,
   `gold_frozen_before_inference:true`). The manifest `status` must be
   `FROZEN`, with each repository `clean_checkout:true`.
7. Run the policy gate and **store the manifest SHA-256**. Only then execute
   any scored model/Gateway benchmark.

~~~powershell
$Source = Join-Path $env:USERPROFILE "pie-dynamic-evidence-planner\source"
$Python = Join-Path $env:USERPROFILE "pie-dynamic-evidence-planner\.venv\Scripts\python.exe"
& $Python (Join-Path $Source "tools\des04_validate_freeze.py") "<path-to-reviewed-frozen-des04.json>"
~~~

The draft deliberately fails this command. Passing a policy gate does not
prove the reviewers examined the source; source-span review is a human
process and should be auditable.

## Evaluation metrics (future scoring harness)

Report independently:
- retrieval precision/recall for source-verified edges, files and line spans;
- exact cross-file graph hops with provenance and number of omitted edges;
- abstention caused by index staleness, ambiguity, unsupported runtime proof,
  or rejection after model invocation;
- overclaims: unsupported causal/breakage assertions (target: **zero**);
- source freshness before and after model inference;
- end-to-end/inference-only latency and token usage (only when measured);
- per-repository results and a held-out corpus never used to tune the planner.

The DES-04 release gate must block merge until real indexed snapshots,
frozen independent gold, cross-file retrieval results and security/CI
regression have all been inspected. PR #11 remains draft, and `main` is
untouched.
