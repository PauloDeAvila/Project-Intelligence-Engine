# Web Intelligence Phase 7 — Action Engine

Phase 7 introduces a controlled execution boundary. It does not invent selectors or let page text become executable instructions.

## Execution sequence

`ActionPlanner → PreflightValidator → SecurityGate (fresh) → ActionDriver → PostActionVerifier → RecoveryController`

- `ActionPlanner` creates a bounded declarative plan from a `TaskIntent` and snapshot-bound reference;
- `PreflightValidator` checks session, generation, snapshot, target and fingerprint immediately before execution;
- `ActionDriver` is an explicit injected boundary, keeping browser-specific behavior outside the core contract;
- `PostActionVerifier` requires an observed completed outcome and an after-snapshot/transition;
- `RecoveryController` requests a fresh snapshot for stale references and never automatically retries non-idempotent actions.

Sensitive input is passed only to the driver call and is not stored in plans, results or recovery records. High-impact actions remain denied by Phase 5 even when an approval record exists.

The current phase is deliberately adapter-neutral. A future browser adapter can implement `ActionDriver` after its own preflight and evidence integration are certified.
