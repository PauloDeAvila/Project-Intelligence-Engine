---
name: independent-review
description: Perform strict evidence-based, read-only architectural and regression impact review using PONTO.md before approval.
---
# Independent review

Read PONTO.md and docs/review-report-template.md fully.

Operate in independent review mode: inspect source, diff, tests and CI results; NEVER edit production files or weaken validation to obtain approval.

For every changed symbol, trace definitions, references, callers, indirect consumers, data contracts and regression exposure. Ground each assertion in file/line or concrete test output; acknowledge unresolved references.

If an independent subagent is available, assign this role to it, withholding write access. Otherwise perform a separate reviewer pass after implementation; do not call it an independent subagent.

Produce the complete report requested by PONTO.md. Approve only on verifiable evidence, passing required checks and no blocking findings.
