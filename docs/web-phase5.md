# Web Intelligence Phase 5 — Security & Permission Gate

Phase 5 separates relevance from authorization. A page element can be highly relevant and remain blocked when its action is risky, stale, cross-origin, unsupported or not explicitly approved.

## Pipeline

`SensitiveDataFilter → OriginGuard → RiskScorer → PolicyEngine → ApprovalManager → final recheck`

The gate returns a bounded `SecurityDecision`; it never starts a browser, executes JavaScript, follows a selector, sends a request or invokes an action adapter.

## Safety rules

- snapshots must be `CURRENT`, candidates must be current, supported, visible, enabled and bound to the same session/page/snapshot;
- origins are canonical exact matches against the session allowlist; malformed URLs, credentials, wildcard hosts and sensitive query keys fail closed;
- page text is untrusted data and cannot grant permission; prompt-injection-like labels are blocked;
- credentials, payment, destructive, external-communication and unknown action surfaces are denied, even with an approval record;
- ordinary mutations (`click`, `select`, `type`, `submit`) require an explicit one-time approval;
- approvals are in-memory, bounded, TTL-limited, fingerprint-bound to session, generation, snapshot, target, origin and policy version, and consumed atomically;
- navigation is bounded by a step limit and remains exact-origin only.

## Output discipline

Decisions contain IDs, categories, bounded risk values and closed reason codes. They do not contain page text, entered values, headers, credentials or raw error messages.

This phase is intentionally authorization-only. Action execution and post-action evidence remain later phases.
