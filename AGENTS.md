# Engineering contract for AI agents

Read this file before every task. PROJECT.md and verified source code define the scope; instructions never replace evidence.

## Non-negotiable rules
1. **Stay in scope.** Determine the requested outcome, affected modules, exclusions and acceptance criteria. Do not expand scope, refactor unrelated components or add speculative features.
2. **Inspect before editing.** Read entry points, callers, tests, interfaces, error paths and architectural boundaries. Do not assume behavior.
3. **Avoid unnecessary abstraction.** Prefer cohesive, minimal changes using existing patterns. New layers, wrappers, interfaces and dependencies require demonstrated value.
4. **Protect contracts and invariants.** Preserve unrelated behavior, public APIs, data formats and compatibility unless explicitly approved.
5. **Map change impact.** Trace dependencies and consumers; identify what might regress before changing code.
6. **Edit narrowly.** Make minimal, reviewable changes and keep unrelated formatting out of the diff.
7. **Mandatory exhaustive verification gate.** No implementation is COMPLETE or READY TO DELIVER until the applicable verification suite has actually been run and passed. Revalidate the whole project progressively: basic functions and unit tests → modules and component tests → integration and contracts → end-to-end user flows → complete regression suite → build/static/security checks as applicable. Always run the entire existing test suite for the repository, not only the modified module. Expand tests to cover changed behavior, regressions, boundaries, error paths and critical invariants. Use the regression-first skill.
8. **Evidence over confidence.** Record exact commands, exit codes, tests executed/skipped/failed, environment and artifacts when available. An assertion of “100% working” is forbidden: passing tests establishes evidence under tested conditions, not universal correctness. Never invent results or silently substitute a small smoke test for a comprehensive suite.
9. **Failed or blocked verification prevents completion.** Diagnose failures, fix only related root causes, and rerun impacted tests AND the full suite. If tooling, hardware, credentials, external services or time make a test impossible, mark the task BLOCKED / NOT VERIFIED, explain what is missing, and do not claim delivery completed. Do not spin indefinitely or conceal limitations.
10. **Never weaken checks.** Do not delete/skip tests, loosen assertions, mock the target behavior to fake success, swallow exceptions, or change baselines merely to pass.
11. **Update only factual documentation.** Keep context maps, architecture decisions and test procedures aligned with observed source.
12. **Escalate meaningful risk.** Seek approval before destructive operations, migrations, security-sensitive changes or major architectural changes.

## Workflow
**Understand → Trace dependencies → Define acceptance & test matrix → Plan → Minimal edit → Tests from low to high level → Full regression → Inspect diff → Evidence report.**

## Completion gate
A task can be reported as **VERIFIED FOR DELIVERY** only if:
- Acceptance criteria have objective checks with passing evidence.
- The full applicable existing automated test suite passes, with no unexplained skips or regressions.
- All affected critical paths are exercised, including expected failure and edge-case behavior.
- Required build, lint, static checks and applicable environment/integration checks pass.
- Results are reported honestly with coverage limitations. No test methodology proves absolute absence of bugs.

Otherwise report **BLOCKED / NOT VERIFIED** and supply results and next steps; never say the work is finished or fully operational.

## Required final report
- Changed files and requested outcomes.
- Dependency and compatibility impact.
- Test matrix by layer; commands and actual outcomes; skipped/blocked checks.
- Risks, unverified scenarios and evidence links/logs if available.

## Context and skills
Read PROJECT.md, docs/context-map.md, docs/architecture.md, docs/decisions.md. Source is authoritative when documents are stale. Apply .agents/skills/regression-first to implementation tasks and the other relevant skills for scope and impact.

## Mandatory CI/bootstrap and independent review
Before feature implementation in each new project, run .agents/skills/ci-bootstrap. Set up a real CI pipeline for its actual stack, then confirm GitHub branch protection/rulesets require PRs and passing checks. The starter CI intentionally fails until real tests are configured: never replace it with a success-only placeholder. If CI or protection cannot be verified, report BLOCKED and do not label the project ready.

For every code change, run .agents/skills/independent-review after implementation. The reviewer MUST follow PONTO.md, trace changed symbols to direct and transitive consumers, inspect tests and the complete diff, and generate the detailed report in docs/review-report-template.md. A separate read-only subagent is preferred if the runtime supports it; otherwise run a clearly separated review phase. Review cannot approve without required test evidence.


## Git publishing and credential safety
When a `git push`, fetch or credential lookup fails or takes excessively long:

1. Do not repeat the same operation indefinitely. Two failed attempts are enough to stop.
2. Do not run `git credential fill` (or any equivalent) to extract tokens, and never capture, print, transmit or handle credentials directly.
3. Do not assemble HTTP `Authorization` headers, credential URLs or other manual authentication transports. Secrets must never enter shell variables, command lines or child-process environments.
4. Use only the official Git credential helper or GitHub CLI (`gh auth setup-git`) authentication paths. Interactive sign-in belongs to the human; the agent must not proxy it.
5. After two failures, stop, preserve local commits and worktrees, and report a technical diagnosis as BLOCKED.
6. Never state that a push, branch or pull request was created without independently confirming the result against GitHub. Verify remote refs (for example the repository branches API) before claiming publication.
