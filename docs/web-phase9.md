# Web Intelligence Phase 9 — Semantic Decision Layer

Phase 9 resolves only the ambiguity that deterministic local rules cannot safely settle.

## Flow

`DecisionBatcher → UncertaintyEstimator → FallbackRouter → optional ClassifierAdapter → deterministic validation`

- local confidence is calculated from relevance score, query/role evidence, ambiguity and protected signals;
- confident candidates stay local and incur zero model calls;
- uncertain candidates request more context unless an external classifier is explicitly provided and enabled;
- sensitive, financial, credential and page-instruction candidates are never sent externally;
- the optional adapter receives only bounded minimized features, not snapshots, credentials, URLs, session data or raw queries;
- classifier outputs are validated for cardinality, reference identity and order before use.

The default route is local. This phase has no provider-specific dependency and does not bypass the Security Gate or Action Engine.
