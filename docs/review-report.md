# Independent code review — Web Intelligence Phase 0

## Identification

- Repository: `PauloDeAvila/Project-Intelligence-Engine`
- Branch: `feat/web-phase0-contracts`
- Base SHA: `ec46d8503aa58cc5071562f119adfbd894b2ce1d`
- Head SHA: the final commit containing this report; verify with `git rev-parse HEAD`
- Reviewer: independent read-only pass, agent `Newton`
- Decision: **APPROVE** for PR, subject to remote CI and protected-branch gates

## Scope and decision

This review covers only Phase 0: dependency-free web contracts and governance. It does not approve browser adapters, CDP, network access, page extraction, MCP web tools, or action execution.

The implementation keeps `pie.web` isolated from the existing Python indexer, browser runtimes and network. Contracts are immutable, versioned, bounded and fail closed. Page-derived text is untrusted and is redacted from serialized artifacts; origins, snapshot references, intent operations, action outcomes and telemetry use explicit allowlists/invariants.

## Main protections

- `BrowserSession` has explicit lifecycle transitions, exact HTTP(S) origins, session/page generation and reconnection requirements.
- Origins reject credentials, wildcard hosts, malformed DNS, legacy numeric IPv4, invalid IPv6 and encoded hosts.
- `PageSnapshot` candidates are bound to session, page, frame, snapshot, hash and generation. STALE/PARTIAL/BLOCKED states propagate to `find()`, elements and JSON.
- `TaskIntent.action` and `expected_transition` are typed declarative fields. `goal` and `target_query` remain literal untrusted text and cannot execute.
- `ActionResult` has a closed matrix for planned, success, blocked, rejected, stale, timeout and separate execution/verification failures.
- Serialization uses `allow_nan=False`, rejects isolated Unicode surrogates, redacts free page/intent text and restricts structural roles, sources, actions and metrics.
- Secret-bearing workflows are manual-only; no workflow combines `pull_request`/`pull_request_target` with `secrets.*`.

## Verification matrix

| Layer | Command | Result |
| --- | --- | --- |
| Web contracts | `rtk test py -3 -m pytest tests/web -q` | 11 passed |
| Full pytest | `rtk test py -3 -m pytest -q` | 345 passed, 2 skipped, 126 subtests |
| Full unittest | `py -3 -m unittest discover -s tests -q` | 347 passed, 2 skipped |
| Project verification | `py -3 tools/verify_project.py` | unit/component/integration/e2e/regression/build passed |
| Install/package | `py -3 tools/check_install.py` | passed; installed package exposed `pie-web-contracts-v1` |
| Compile | `py -3 -m compileall -q src tools tests` | passed |
| Diff hygiene | `git diff --check` | passed |
| Secret workflow scan | PowerShell scan for `pull_request` + `secrets.*` | passed; zero matches |

The two skipped tests are Windows symlink cases unavailable without the required privilege. The independent review also confirmed import isolation from browser/network/subprocess effects and 11/11 web contract tests.

## Governance status

- `Protect main` ruleset is active and PR-only.
- The current ruleset still requires only `Project Verification`; Windows and web checks must be added after the PR exposes their exact check contexts.
- Strict branch update policy must be enabled before merge.
- CODEOWNERS and SECURITY.md are present. Private vulnerability reporting is not assumed enabled; SECURITY.md documents the fallback.

## Residual risk and next phase

Phase 0 does not provide browser functionality. The next phase must add an adapter behind these contracts, with fake-adapter security tests first, then controlled CDP/Playwright integration, origin enforcement, page intelligence and evidence quantification. No web action should be enabled by this change alone.
