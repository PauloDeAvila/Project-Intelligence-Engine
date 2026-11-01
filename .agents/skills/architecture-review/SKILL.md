---
name: architecture-review
description: Review responsibilities, dependencies, duplication, and architectural fit without inventing layers or rewriting stable systems.
---
# Architecture review

1. Read the architecture file and inspect the real code before drawing conclusions.
2. Identify responsibility boundaries, coupling, cycles, redundant logic, and fragile contracts with file-level evidence.
3. Distinguish observed defects from hypotheses and aesthetic preferences.
4. Prefer reducing complexity over adding new abstractions; propose an abstraction only when supported by concrete duplication or change pressure.
5. Recommend staged, reversible changes with risk, verification, and explicit out-of-scope items.
6. Unless implementation is requested, deliver diagnosis and a plan only.
