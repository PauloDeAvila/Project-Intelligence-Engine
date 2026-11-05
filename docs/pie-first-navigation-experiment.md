# PIE-First experimental policy (Graphify-inspired)

Reference: https://github.com/Graphify-Labs/graphify, namely
`graphify/cli.py` hook-guard and `graphify/always_on/agents-md.md`.

This experiment **does not install an actual Codex hook**, modify AGENTS.md,
change the PIE MCP, force a search engine, or restrict access to source files.
It models a tiny opt-in policy as a pure typed Python function and runs a
deterministic trace replay to test routing safeguards in isolation.

Rules: Prefer PIE for indexed codebase-navigation queries; deny only the
first indexed raw read/grep in optional strict mode; allow source edits,
execution tests and necessary source inspection. Do not block when the
index is stale, the file is not indexed, or the target is external.
The caller MUST verify freshness; this pure module cannot do so.

Validation:
- Pyright on the new strict typed policy (CI).
- New safety tests + full Linux regression (CI).
- 9-scenario offline replay with an explicit distinction between suggested
  redirects and observed tool calls.
- No real agent session or model provider is invoked, so savings remain
  **UNKNOWN**, never estimated as actual token/cost improvements.
- No runtime integration until a real A/B with the same agent, questions,
  source tree, tool affordances and certified outcomes shows improvement.

Existing architecture and main behavior remain intact.
