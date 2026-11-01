---
name: change-impact
description: Analyze the blast radius of a bug fix or feature before touching code so that one fix does not break an unrelated component.
---
# Change impact analysis

1. Identify the behavior, its entry point, and its contract.
2. Trace callers, callees, data transformations, persistence, configuration, and error handling.
3. Enumerate invariants and backwards-compatibility obligations.
4. Build a concise impact matrix: changed components, dependent consumers, potential failure mode, protective test.
5. Classify risk: low (local), medium (shared internal), high (public contract, storage, security, migrations).
6. Choose the smallest change that preserves existing contracts. For high risk or uncertain impact, seek approval before editing.
7. Verify changed and neighboring workflows after implementation.
