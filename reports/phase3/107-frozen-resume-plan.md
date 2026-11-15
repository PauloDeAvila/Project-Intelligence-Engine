# PIE Phase 3 — Frozen A/B Resume Readiness

## Status

`READY_FOR_PAID_AB` for the execution plan only. Model execution remains disabled and no quota was consumed.

## Offline corrections validated

- `run_single` now propagates the manifest repetition instead of hard-coding repetition 1.
- Web v2 accepts the required navigation and snapshot calls; `pie_gateway_output_get` is optional recovery evidence.
- The controller accepts the Web `exact_text` oracle and validates its fixture text without storing prompts or answers.
- Manifest 106 expands to ten sessions in the frozen order, with one shared `pair_id` per domain and unique `run_id` values per session.

## Frozen execution order

1. Blender R2 optimized, baseline
2. Blender R3 baseline, optimized
3. Web R1 baseline, optimized
4. Web R2 optimized, baseline
5. Web R3 baseline, optimized

The machine-readable plan is [107-frozen-resume-plan.json](107-frozen-resume-plan.json). It records `model_execution: DISABLED` and `automatic_retry: false`.

## Validation

- Focused controller/live tests: 33 passed.
- Resume-plan CLI: exit code 0; 10 sessions emitted; run IDs unique.
- Provider tokens: not collected in this offline step.
- Paid Codex sessions: none executed.

## Reproduction

```powershell
uv run python -m pie.certification.controller resume-plan `
  --manifest reports/phase3/106-frozen-ab-manifest.json `
  --output reports/phase3/107-frozen-resume-plan.json
```

This report does not certify token savings and does not change the frozen scenarios or quota state.
