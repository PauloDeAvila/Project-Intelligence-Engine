---
name: ci-bootstrap
description: Establish suitable real tests, a reproducible GitHub Actions CI workflow, and branch protection before beginning feature development.
---
# CI bootstrap before features

1. Inspect PROJECT.md, stack, dependency/install commands and actual test/build tooling. Never guess runnable commands.
2. Create a minimal but REAL automated test suite where missing; do not invent passing tests.
3. Configure .github/workflows/ci.yml with install, lint/typecheck, unit/component/integration tests, full regression suite and build as applicable. Mark unavailable tiers as explicit blockers rather than substitute echo placeholders.
4. Document local commands and CI parity in PROJECT.md.
5. Validate workflow syntax and run checks; record evidence.
6. Configure repository branch protection/ruleset requiring PR, successful required checks, and suitable reviewer approval using available supported GitHub administration tooling, or instruct the repository owner through exact UI steps when automation isn't supported.
7. Verify protection actually took effect before declaring bootstrap complete. CI configuration alone does not enforce protected branches.
8. Do not start feature coding while mandatory bootstrap remains BLOCKED without explicit user authorization to proceed with that risk.
