# Web Intelligence Phase 10 — Integration and Certification

Phase 10 composes the local web pipeline behind a typed bridge with distinct permissions:

- `pie_web_observe`: bounded read-only page metadata;
- `pie_web_context`: quantified, provenance-rich evidence pack;
- `pie_web_plan`: declarative plan, no execution;
- `pie_web_execute`: explicit execution boundary requiring an injected driver and the Security Gate.

The bridge is `WebIntelligenceService`. It does not own a browser process or silently connect to MCP; a host may register these typed capabilities with its transport.

## Certification result

The automated certification covers the local snapshot → relevance → evidence-pack pipeline on Windows and Ubuntu, with zero model/network calls and `execution_authorized=false`.

It does not claim a live direct-Playwright A/B baseline or a live external MCP browser transport. Those remain explicit follow-up work rather than inferred success.
