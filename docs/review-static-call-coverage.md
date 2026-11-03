# Independent code review — static call coverage

## Identification and executive decision

- Repository: `PauloDeAvila/Project-Intelligence-Engine`.
- Branch: `codex/fix-static-call-coverage`.
- Base: `3fed2ef0b69e29a10d41b96f5846ca4e776dfcbd`.
- Implementation commit: `57a8b7787a146b789b6baf583ee32e8d1813aa8a`.
- Reviewer: separate read-only subagent following `PONTO.md` and
  `.agents/skills/independent-review/SKILL.md`; no production/test files edited.
- Report recorded by the implementing agent from the reviewer's final report.
- **Decision at review time: no remaining blocking code findings; submission
  suitable for review, final delivery approval awaits hosted CI.**
- PR: #13, targeting the DES-04 development branch; no merge/auto-merge.

The implementation fixes local-import reference coverage structurally, adds
qualified method definition queries and versions the truthful coverage contract.
The reviewer's initial ordering finding was corrected and independently retested.

## Changed files, symbols and impact traceability

| File/symbol | Direct and indirect consumers/contracts | Evidence and residual risk |
| --- | --- | --- |
| `analysis/resolver.py`: `_effective_site`, `resolve`, `_resolve_name`, `_resolve_attribute` | Index refresh -> stored usages -> reverse references, graph/context queries -> evidence counts/MCP/Gateway | Imports follow lexical owner; ordering considers line/column; parameter/assignment shadowing remains separate. Static syntax does not prove branch execution. |
| `analysis/definitions.py`: `DefinitionCollector.visit_Delete` | Definition collection -> persisted unbinding site -> effective binding lookup | Later calls lose deleted import targets; the deletion usage still targets the preceding binding. Attribute/subscript deletion does not unbind the base name. |
| `storage/database.py`: `ANALYSIS_VERSION` | Freshness checks and index refresh | Version 4 forces derived-analysis regeneration. Old indexes must be rebuilt in working copies. |
| `retrieval/evidence.py`: `build_evidence` | Context Pack, MCP evidence tool, Gateway, guard rendering | Exact qualified selection, leaf signature extraction, method support and ambiguity/truncation refusal. Instance receiver inference remains unsupported. |
| `retrieval/context_pack.py`: coverage construction/`finalize` | CLI/MCP Context Pack -> downstream clients | v2 separates result omission from partial analysis. v1 consumers require migration. |
| `interfaces/cli.py`, `interfaces/mcp_server.py` | CLI help/tool discovery -> caller-supplied symbol | Qualified method and partial-coverage descriptions match actual behavior. Trusted launch root contract preserved. |
| Three test modules and real-project validation tool | Regression, stdio MCP, disposable indexed projects | Tests cover positive and negative paths; real-project expected lines target the evaluated revisions. |
| Context map, contract and validation docs | Reviewers/consumers | Document observed behavior and compatibility, not universal guarantees. |

Existing Gateway/guard canonical fields (`signature`, `path`, `line` and verified
counts) are retained. Context Pack-specific coverage changes do not change guard
fact selection. Dynamic/reflexive uses are acknowledged gaps, not a claimed
exhaustive consumer map.

## Findings

### R1 — P2/high confidence, resolved

Initial probes reproduced false verified edges for same-line calls before local
imports and eager comprehensions before their enclosing import. The original
guard compared only line numbers and only identical owner/usage scopes.

Independent final probes observed:

| Probe | Final result |
| --- | --- |
| `audit(1); from .quality import audit` | unresolved, no target |
| `q.audit(1); import pkg.quality as q` | unresolved, no target |
| Eager comprehension preceding enclosing import | unresolved, no target |
| Local import deleted before later call | unresolved, no target |
| Same-line call after local import | verified, correct indexed target |

The fix uses source positions across lexical owners and unbinding markers.
Deferred forward closures are conservatively unresolved; this limitation is
explicit rather than misrepresented as runtime ordering proof.

No remaining blocking defect was identified in the final reviewed diff.

## Execution matrix

Reviewer inspected `verification-results.json`, the complete final verification
log and the real-project JSON artifact. Environment: Windows/Python 3.13.17.

| Layer | Command | Outcome |
| --- | --- | --- |
| Unit | `python -m unittest discover -s tests -p test_pie_unit.py -v` | 14 passed |
| Component | `python -m unittest discover -s tests -p test_pie_symbols.py -v` | 55 passed |
| Integration | `python -m unittest discover -s tests -p test_pie_integration.py -v` | 10 passed |
| E2E | `python -m unittest discover -s tests -p test_pie_e2e.py -v` | 1 passed |
| Full regression | `python -m unittest discover -s tests -v` | 300 run, OK, one explained skip |
| Build/install | `python tools/check_install.py` | exit 0 |
| Complete matrix | `python tools/verify_project.py` | six tiers passed |
| Compilation | `python -m compileall -q src tools tests` | implementer observed exit 0 |
| Diff hygiene | `git diff --check` | reviewer independently observed exit 0 |
| Real stdio MCP | `tools/validate_static_context_projects.py` | inspected unchanged-source hashes and successful packs |

The new regression module has 16 tests; the stdio MCP module has five tests.
Both run in the complete suite. The Windows skip is the existing symlink-escape
test: the runner cannot create symlinks. Linux hosted CI remains necessary for
that platform-specific path. No assertion was removed or weakened to pass.

## Real-project and subsystem acceptance

- Doctor Mesh: 45 copied Python files; unchanged original source snapshot.
  `audit_component` has six verified sites, including `capture.py:115` and
  `ui.py:627`. `MeasurementCache.get` identifies `cache.py:26`, binding
  `ai_mesh_doctor/cache.py::class:MeasurementCache::get` and signature
  `def get(self, key):`; zero verified instance callers is explicitly partial.
- Requests: 36 copied Python files; unchanged original source snapshot.
  `extract_cookies_to_jar` retains six sites at `adapters.py:365`, `auth.py:270`,
  `sessions.py:240,276,716,718`, with definition `cookies.py:124`.
- All inspected packs use v2, `static_analysis_coverage=PARTIAL` and
  `exhaustive=false`. No analyzed project code was imported or executed.

## Branch protection and verdict

GitHub ruleset 26297201 was confirmed active for the default branch: PR and
`Project Verification` required, force-push/deletion prohibited, no bypass
actors. Existing approval count is zero; no governance changes were made.

Local acceptance evidence passes and R1 is resolved. The remaining limits are
unknown instance receivers, reflection/dynamic dispatch, external callers,
runtime rebinding, branch reachability and conservative forward closures.
Qualified definition lookup does not establish exhaustive method callers.
Context Pack v2 is an intentional documented client migration.

Hosted CI on the committed PR head was pending at this independent review.
The implementing agent must inspect those checks before claiming final remote
verification. CI success is evidence under tested conditions, not proof of
absence of bugs. **No automatic merge.**
