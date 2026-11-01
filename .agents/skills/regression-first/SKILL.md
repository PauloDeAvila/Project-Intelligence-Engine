---
name: regression-first
description: Enforce rigorous incremental testing from individual functions to full system regression, requiring objective evidence before delivery.
---
# Regression-first and whole-project verification

## Phase 1 — Baseline
- Read PROJECT.md verification commands and identify the actual test/build configuration.
- Map all existing test tiers, modules, critical journeys, external dependencies and prerequisites.
- Capture the baseline: run the existing suite before edits when practical; distinguish pre-existing failures.
- If no tests exist, propose and implement appropriate tests for the task; lack of tests is not proof of correctness.

## Phase 2 — Test matrix
Map each acceptance criterion and affected invariant to checks across these levels:
1. Unit: primitive functions, pure logic, boundary values, invalid inputs, error cases.
2. Component: interaction among functions and state within each affected subsystem.
3. Contract/integration: APIs, persistence, data shapes, IO, third-party boundaries.
4. End-to-end: full supported user workflows, including negative paths when feasible.
5. Regression: execute the complete existing suite for the entire repository, including previously untouched modules.
6. Nonfunctional checks: lint/typecheck/build, plus performance, security, reliability or compatibility tests where relevant.
For levels that do not apply, document the reason instead of silently omitting them.

## Phase 3 — Implement and validate
- Reproduce the defect or specify expected behaviors first.
- Add or improve automated regression tests whenever feasible.
- Make the smallest fix that preserves contracts.
- Execute tests progressively from basic functions to advanced workflows, then rerun the full suite.
- When failures appear, identify the cause, repair without scope creep, rerun targeted tests and repeat global verification.
- Test failures that predate the change must be documented and cannot be silently counted as passing.

## Phase 4 — Evidence and release gate
Record: commands, exit status, totals (passed/failed/skipped), environment, scope, coverage gaps, relevant logs/artifacts.
- VERIFIED FOR DELIVERY only when all required checks pass with evidence and documented limitations.
- BLOCKED / NOT VERIFIED when required checks fail or cannot run; explain the blocker and reproducible next steps. Never misrepresent partial verification as completion.
- Never claim 100% universal correctness; rigorous testing reduces risk, not to zero.
- Never weaken/remove checks or fabricate outcomes.
