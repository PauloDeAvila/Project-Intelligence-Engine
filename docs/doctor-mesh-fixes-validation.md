# Doctor Mesh regression fixes — validation record

Date: 2026-11-03. Development branch: `codex/fix-static-call-coverage`.
Base: `feat/des04-static-traceability-evaluation`, commit
`3fed2ef0b69e29a10d41b96f5846ca4e776dfcbd`.

## Root causes and changes

1. `analysis/resolver.py` followed imported names only when the binding owner
   was module scope. Local import usages instead targeted the local import
   definition, so reverse lookup for the exported callable missed them. Imported
   attribute access similarly rejected local owners before inspecting whether
   their binding was an import. Both now follow indexed imports from their
   lexical owner, preserving alias/re-export provenance and ambiguity refusal.
   The source-position guard includes columns and enclosing comprehension
   scopes; it conservatively refuses reads preceding local imports. Name
   deletions in `analysis/definitions.py` invalidate later resolutions, while
   the deletion usage itself retains its preceding binding target.
2. `retrieval/context_pack.py` computed `complete_direct_call_list` solely from
   output truncation. v2 removes that field, adds
   `returned_verified_call_list_complete`, `static_analysis_coverage=PARTIAL`
   and `exhaustive=false`. Counts and both omission causes remain explicit.
3. `retrieval/evidence.py` required `isidentifier()` and filtered out methods.
   It now validates dotted identifier components, rejects keywords, selects
   exact stored qualified names, includes method definitions, extracts the
   leaf-name signature, and refuses ambiguous or truncated definition lookups.
4. `storage/database.py` bumps analysis rules to 4 so old derived references
   cannot silently survive the resolver change. MCP descriptions and CLI help
   document qualified callables; consumers must migrate Context Pack v1 to v2.

Additional files: `tests/test_static_call_coverage.py`,
`tests/test_des04_context_pack.py`, `tests/test_des04_mcp_stdio_e2e.py`,
`tools/validate_static_context_projects.py`, `docs/context-map.md` and
`docs/des04-context-pack-mcp.md`.

## Baseline and regression-first evidence

Environment: native Windows, Python 3.13.17; runtime dependencies remain
standard-library only. Baseline: `python -m unittest discover -s tests -v`,
exit 0, 282 tests, one pre-existing symlink skip. The new regression module was
run before production edits: exit 1, eight initial tests, eleven subtest
failures and one error, reproducing the import/method/coverage defects.

The independent reviewer reproduced same-line and eager-comprehension
pre-import false positives in the first fix. Those probes were added to the
regressions and corrected. Deletion handling initially broke the existing
deletion-usage target invariant; the implementation was corrected and the
unchanged existing assertion now passes. Failed intermediate runs are not
counted as passing validation.

## Final local matrix

`python tools/verify_project.py` exited 0 with all six required tiers passed:

| Tier | Exact command | Result |
| --- | --- | --- |
| Unit | `python -m unittest discover -s tests -p test_pie_unit.py -v` | 14 passed |
| Component | `python -m unittest discover -s tests -p test_pie_symbols.py -v` | 55 passed |
| Integration | `python -m unittest discover -s tests -p test_pie_integration.py -v` | 10 passed |
| E2E | `python -m unittest discover -s tests -p test_pie_e2e.py -v` | 1 passed |
| Full regression | `python -m unittest discover -s tests -v` | 300 run; 299 passed, 1 skipped; 25.839s |
| Build/install | `python tools/check_install.py` | exit 0, fresh virtualenv package install and installed CLI flows |

`python -m compileall -q src tools tests` and `git diff --check`: exit 0.
`python tools/benchmark_index.py --files 100`: exit 0, 100 files/200 symbols,
0.5054s indexing, 20 searches in 0.0497s. This is a local reproducibility smoke,
not proof of performance or token savings.

The full suite includes real MCP subprocess tests for handshake/discovery,
local-import/comprehension callers, qualified method signatures, v2 coverage,
malformed/ambiguous symbols, stale snapshots and rejected root overrides.
The sole skipped test is the existing symlink-escape test because native
Windows symlink creation is unavailable on this runner; hosted Linux CI is
needed to exercise that platform-specific test.

## Real-project execution

Command (use the evaluated snapshot locations for ROOT arguments):

```text
python tools/validate_static_context_projects.py --doctor-mesh DOCTOR_ROOT --requests REQUESTS_ROOT --output RESULT_JSON
```

Exit 0. The tool copies eligible Python bytes into disposable temporary
projects, indexes only those copies, executes actual `pie.interfaces.mcp_server`
processes through JSON-RPC stdio, and compares original source bytes before/after.
No analyzed modules execute. Original `.pie` indexes are not opened for writing.

| Project | Copied Python files | Checked result |
| --- | --- | --- |
| Doctor Mesh | 45 | `audit_component`: six verified calls; `MeasurementCache.get`: exact definition/signature/hash, zero verified instance callers |
| Requests | 36 | `extract_cookies_to_jar`: six verified calls |

Doctor Mesh `audit_component` locations: `ai_mesh_doctor/batch.py:62`,
`capture.py:115`, `ui.py:627`, `tests/test_efficiency.py:118,119,122`.
Requests locations: `src/requests/adapters.py:365`, `auth.py:270`,
`sessions.py:240,276,716,718`; definition `cookies.py:124`.
All returned known calls fit the configured budget; every caller hash matched.
Both original source snapshots remained unchanged. Historical reference
artifacts were not edited. Full hash/pack evidence was saved outside this repo
in `pie-doctor-mesh-evaluation/fixed-real-projects.json` under the user's profile.

## Remaining limits and review gate

This is static binding evidence, not control-flow dominance, execution,
dynamic dispatch or behavioral-impact proof. Unknown instance receivers,
reflection, runtime rebinding and external code remain outside verified
coverage. Textually forward deferred closures may be conservatively unresolved.
Qualified method lookup does not certify all method callers; zero verified
callers must not be interpreted as zero uses. Tokens/latency savings were not
measured. Reindex working copies for analysis version 4 and update v1 consumers.

The default-branch ruleset `Protect main` (26297201) was confirmed active via
GitHub API: PR required, `Project Verification` required, no bypass actors,
force-push/deletion prohibited. Existing required approval count is zero; it
was not changed. No merge or auto-merge is authorized by this validation.
Hosted CI and the independent review report are separate evidence gates.
