# Web Intelligence Phase 6 — Web Evidence Packs

Phase 6 delivers compact, traceable context to a model after relevance filtering and independently of authorization.

## Pack contents

- snapshot/session/page provenance, origin, generation and hash;
- selected references with sanitized labels, semantic role, region and declarative actions;
- relevance score and risk categories;
- permission state as an observation only (`NOT_CHECKED`, `ALLOWED`, `APPROVAL_REQUIRED`, `BLOCKED`);
- explicit omission ledger with bounded reasons and expandable references;
- strict character budget and a deterministic expansion plan.

`execution_authorized` is structurally fixed to `false`. A pack is not an action plan and cannot bypass the Security Gate.

Sensitive labels are replaced by bounded markers. Raw credentials, entered values, page-instruction text and other secret-bearing content are not copied into the pack.

Stale or blocked snapshots cannot be packed. Partial snapshots may be delivered only with their omission state preserved.
