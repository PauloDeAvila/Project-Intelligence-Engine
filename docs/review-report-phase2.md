# Independent review report — Web Intelligence Phase 2

## Decision

**PASS for PR, pending remote CI and protected-branch gates.** This review
covers bounded Page Intelligence snapshots only. It does not approve ranking,
semantic search, action execution, Evidence Packs, or arbitrary browser
automation.

## Scope reviewed

- inert accessibility-tree and fixed-locator DOM extraction;
- deterministic normalization, hashing and snapshot-bound references;
- explicit `SUPPORTED`/`UNSUPPORTED` element state;
- literal role/name lookup without model-provided selectors;
- generation/frame authority and stale-state tracking;
- bounded input, element, depth and text handling;
- Playwright integration against a local HTTP fixture.

## Security findings resolved before this report

The independent security pass identified and the implementation resolved:

- snapshot-ID collision and current-authority replacement in the registry;
- resolution without exact frame, generation, hash and current-authority binding;
- forced `CURRENT` state when extraction omitted elements;
- traversal beyond the element budget and unbounded input-node traversal;
- unsupported elements exposing actions or arbitrary reason text;
- loss of `dom_snapshot` provenance in DOM-derived records.

The final contracts reject these states rather than silently repairing them.

A second independent security review returned **PASS** after the fixes, covering
authorized extraction, stable page identity, depth/action bounds and atomic
registry resolution.

## Local verification

| Layer | Result |
| --- | --- |
| Web unit/integration suite | 41 passed |
| Full unittest suite | 377 passed, 2 skipped |
| Project verification | unit/component/integration/e2e/regression/build passed |
| Install/package check | passed; package built and installed |
| Compile | passed |
| Diff hygiene | passed |
| Browser runtime | Playwright 1.64.1 with local Chromium passed |

The two skipped tests are existing Windows symlink cases requiring a
privilege not available in the test environment. No HTML, raw DOM, page
responses or secrets are emitted by the Phase 2 tests or artifacts.

## Explicit limits and non-goals

- Default extraction is bounded at 512 page elements and 2,048 input nodes.
- Unknown semantic roles remain visible as unsupported data without actions.
- Page text is untrusted and is not interpreted as a selector, script or
  authorization.
- The current phase does not quantify relevance, rank evidence, execute
  actions, or access arbitrary URLs from model input.
