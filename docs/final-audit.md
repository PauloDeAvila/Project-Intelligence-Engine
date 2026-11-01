# PIE V0.1 audit — 2026-10-31

## Status: V0.1 STABILIZED — PRODUCTION GATE IMPROVED
This is an evidence-based record, not an unconditional certification.

## Verified from GitHub
- GitHub Actions recognized and ran the Validation Gate workflow: run 41254815589.
- "Starter Unit Tests" job succeeded in that run; this establishes a successful execution for the then-existing tests.
- The local verification matrix now executes unit, integration, E2E, regression and build checks; the component tier is explicitly not applicable for V0.1.
- A subsequent commit 0fca3892c99022991a4cfe178f79c93a961ab352 added tests for command success, failure, missing executable, result evidence, and fail-closed configuration. Refer to Actions for the outcome of this newer run; do not assume it passed.
- GitHub UI now shows active ruleset `Protect main`, targeting the default `main` branch and requiring pull requests plus `Project Verification`.

## Implemented controls
- Agent engineering contract (AGENTS.md), scope guard, dependency impact analysis and full regression rules.
- Read-only reviewer protocol (PONTO.md) with detailed report template.
- Project bootstrap and independent-review agent skills.
- Python verification runner, six named test tiers, JSON result evidence, and GitHub Actions job.
- Branch protection setup and verification guide (docs/branch-protection.md).
- V0.1 Python package, SQLite index, CLI workflow and tests.

## Known gaps
1. V0.1 intentionally supports Python only; additional languages require new adapters and tests.
2. The verification runner cannot prove full functional coverage just by running commands. A project's test design, coverage and independent review remain essential.
3. Branch rulesets must be configured in GitHub and enforcement validated via a failing PR and a passing PR.
4. A failing-PR enforcement test remains a follow-up; the active ruleset configuration is verified in the GitHub UI.
5. A separate autonomous review agent is not running as a service. The skill defines the process for an independent read-only reviewer when supported.

## Required acceptance evidence for a new project
- Actual checks specified in ci/checks.json; execution results attached.
- Successful unit, component, integration, E2E and full regression checks as applicable, with exclusions justified.
- A reviewed change-impact report identifying relevant direct and indirect references.
- GitHub ruleset active for main, requiring PR and passing Project Verification status.
- Evidence that a failing PR cannot be merged.

## Local verification evidence
- Bundled Python 3.12 runtime: complete regression suite passed, 23 tests.
- `tools/verify_project.py`: unit passed, component not-applicable, integration passed, E2E passed, regression passed, package-install build passed.
- `python tools/check_install.py`: package installed into an isolated target and imported successfully.
- `python tools/benchmark_index.py`: baseline recorded for 100 files and 200 symbols in 0.0441 seconds on the local runtime.
- `python -m compileall -q src tools tests`: passed.
- `.gitignore` patterns, snapshot parsing, literal `LIKE` escaping, Unicode paths, unreadable-file handling, concurrent-read behavior and SQLite integrity are covered by the expanded 23-test suite.

## Conclusion
The V0.1 functional slice is locally verified under the recorded commands. The active branch ruleset and CI matrix now address the principal governance gaps; a deliberately failing PR should still be used as the final enforcement proof.
