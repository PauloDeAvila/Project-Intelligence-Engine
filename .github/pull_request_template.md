## Objective and limits
- Requested behavior and acceptance criteria:
- Explicitly out of scope:

## Impact analysis
- Changed components and dependent consumers:
- Interfaces, data contracts and invariants preserved:
- Risks and regression-sensitive workflows:

## Progressive verification matrix
| Layer | Command / scenario | Actual result | Evidence / blocker |
| --- | --- | --- | --- |
| Unit / basic functions | | | |
| Component / subsystem | | | |
| Contract / integration | | | |
| End-to-end workflows | | | |
| **Full repository regression suite** | | | |
| Build / lint / typecheck / applicable nonfunctional | | | |

## Delivery gate
- [ ] Tests for new behavior, boundary cases and regressions are included
- [ ] All existing repository tests executed and passed (or task marked blocked)
- [ ] Affected critical workflows validated
- [ ] Failures, skips and unavailable tests explicitly documented
- [ ] Diff inspected for unrelated edits, contract breaks and unnecessary abstractions
- [ ] Documentation updated where the architecture/behavior genuinely changed
- [ ] Evidence collected for each required layer

**Status:** VERIFIED FOR DELIVERY / BLOCKED — NOT VERIFIED

Passing tests does not prove zero bugs. Never state “100% working” without qualification.
