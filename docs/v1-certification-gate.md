# PIE V1 — certification gate (candidate, not released)

This gate is **fail closed**. A passing unit suite is necessary but not sufficient to tag V1.0.

## Reproducible deterministic layer (no LLM, no 9Router)

Run with Python 3.12+ from the repository root:

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
python tools/verify_project.py
python tools/benchmark_index.py --files 5000 --queries 100
```

The source fixture in `tests/test_reference_usage_kind.py` exercises a code pattern
found during the Doctor Mesh investigation: an imported `analyze_mesh` function
called directly in tests, passed as an argument, and bound to an alias.
Checks include:

| ID | Deterministic requirement | Regression |
| --- | --- | --- |
| G01 | Exact definition is discoverable | `test_exact_definition_is_located` |
| G02 | Direct `Call.func` is classified distinctly | `test_direct_call_alias_value_and_argument_are_distinct` |
| G03 | Alias invocation is not misrepresented as a direct call to its source binding | `test_alias_invocation_is_not_mislabeled_direct` |
| G04 | Passing a symbol as an argument is not called a direct invocation | `test_direct_call_alias_value_and_argument_are_distinct` |
| G05 | Imported references resolve to the original definition | `test_import_resolution_preserves_original_target` |
| G06 | Unknown symbols cannot manufacture consumers | `test_negative_lookup_does_not_invent_references` |
| G07 | Changed consumer source cannot return old verified rows | `test_modified_source_does_not_return_verified_stale_evidence` |
| G08 | Changed definition invalidates reverse proof | `test_changed_definition_invalidates_reference_proof` |
| G09 | Incremental reindex restores current evidence | `test_reindex_recovers_current_evidence` |
| G10 | MCP requires expected arguments and rejects extras | `test_missing_required_mcp_argument_is_rejected`, `test_mcp_rejects_unknown_arguments`, `test_mcp_status_accepts_empty_arguments` |

`usage_kind` is derived from the AST **only for hash-verified source rows**.
It supplements, and never upgrades, the existing `resolution` field.
`direct_call` means a direct syntactic `Name(...)` call, not proof that
a dynamic dispatch will always execute at runtime.

## Real repository / incremental gate

On a **disposable copy** of the same pinned Python repository for every scenario:

1. Record repository commit, Python version, PIE commit, OS, file count and SHA-256 of all source files.
2. Initialize/index and record `pie status` and deterministic search answers.
3. Apply one controlled change to a consumer call; demand that old verified evidence is rejected.
4. Reindex incrementally, demand `CURRENT`, and verify the revised call sites.
5. Restore the repository to the pinned commit; repeat on Windows and Linux.
6. Run MCP initialization, `tools/list`, valid tool calls, invalid arguments and an out-of-root path check.
7. Record benchmark command, runtime, returned rows, omissions and diagnostics in CI artifacts.
8. Require human review of any new `unresolved` edges or evidence disagreement.

## Qwen + PIE question battery — separate evaluation

Do **not** use LLM responses as a golden answer. Have a reviewer or a deterministic
AST-based oracle establish paths, call sites, signatures and expected behavior first.

Freeze the Doctor Mesh commit before running questions Q01–Q10:

| ID | Question target | Ground-truth requirement |
| --- | --- | --- |
| Q01 | Find `analyze_mesh` | Exact file, signature and range |
| Q02 | Find direct callers | Exact AST call expressions, not merely `load` |
| Q03 | Differentiate imports vs calls | Independent enumeration by source |
| Q04 | Locate nested functions | Qualified name and source span |
| Q05 | Trace imports across modules | Proven binding and consumer |
| Q06 | Assess mandatory signature parameter | All verified affected call sites |
| Q07 | Handle nonexistent symbol | No invented file or caller |
| Q08 | Handle stale file | Reject drifted evidence and diagnose |
| Q09 | Reindex after a controlled edit | Verify new evidence replaces old |
| Q10 | Explain unresolved dynamic/external edges | Clearly distinguish verified vs unresolved |

Run each question in a **fresh session**, three repetitions per condition:
A) direct Filesystem, B) PIE legacy, C) PIE candidate. Same local model,
quantization, context, max output tokens, temperature and pinned workspace.
Capture tool call count, success/failure, evidence precision/recall against
oracle, total latency, input/output tokens and raw tool payload sizes.
A handoff/compaction is not proof of correctness. Report unanswered cases and
separate model errors from indexing/transport errors.

## Release acceptance (all required)

- Linux and Windows CI green, including complete unit/integration/MCP/security suites.
- No false VERIFIED claims or stale-hash disclosure in controlled oracle cases.
- Contract validation covers malformed/unknown MCP arguments and path isolation.
- Deterministic benchmark artifacts and reproducible real-repository runs published.
- Q01–Q10 answered and scored against the independently reviewed oracle.
- Performance budgets set **before** release evaluation, with p50/p95 and memory footprint.
- Independent code review, migration/rollback tests and release notes approved.
- Only after these pass: update version metadata, create an immutable tag and release artifacts.

**Current status:** candidate in development; these documents do not certify V1.
