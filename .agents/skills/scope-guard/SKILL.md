---
name: scope-guard
description: Keep an implementation inside the requested scope, preventing speculative abstractions, unrelated refactors, and scope creep.
---
# Scope guard

1. Extract the user-requested outcome, allowed files/behaviors, exclusions, and acceptance criteria.
2. Read PROJECT.md; flag conflicts instead of silently widening scope.
3. For each proposed change ask: is this necessary to meet an acceptance criterion? If not, defer it.
4. Prefer direct, local, idiomatic code; require a concrete second use-case or proven architectural benefit before introducing reusable abstractions.
5. Review the final diff for unrelated changes, unnecessary dependencies, premature generalization, and accidental public API modifications.
6. Report any deferred improvements separately, without implementing them.
