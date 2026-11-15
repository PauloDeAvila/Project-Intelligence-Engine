# PIE Phase 3 — Offline compaction acceptance

Result: `COMPACTION_READY_FOR_AB`.

This phase was intentionally offline. No Codex session was started, no quota was consumed, and no persistent MCP configuration was changed. It validates the safety and recovery contract required before another paid A/B attempt; it does not certify token savings.

## Evidence

| Check | Result | Evidence |
|---|---|---|
| Small output passthrough | PASS | Existing differential pair records `PASSTHROUGH`; source and returned character counts are equal. |
| Large Blender output | PASS | `DomainStdioTests.test_blender_bridge_tools_and_write_outputs_are_preserved`; large repeated scene observation becomes `PARTIAL`, while the write result remains unchanged. |
| Large Web output | PASS | `DomainStdioTests.test_web_navigation_is_called_once_and_recoverable`; required refs remain in the preview and the full sanitized output is recoverable. |
| Recovery integrity | PASS | The recovered Web payload SHA-256 matches the deterministic fixture snapshot. |
| Duplicate upstream calls | PASS | Marker assertions remain `11` for the two Blender calls and `11111` for the five Web calls. |
| Hidden tool calls | PASS | Selective exposure lists only the allowlisted tools and rejects hidden calls before forwarding. |
| Provider tokens | NOT RUN | This phase made zero model calls by design. |

## Fixtures

- Web: [large.html](../../fixtures/phase3/web/large.html), a local deterministic product page with stable element ids and labels.
- Blender: [large_scene_spec.json](../../fixtures/phase3/blender/large_scene_spec.json), a deterministic 64-object/16-material specification. It is not applied to a live scene.

The Web gateway test uses a deterministic Playwright-style snapshot directly so the compaction and recovery behavior is isolated from browser availability. The fixture is retained for the subsequent local-browser A/B setup.

## Interpretation

The safety gate is ready for a fair A/B run: compact only large eligible observations, preserve small/error/image/write responses, expose only the tools needed by the scenario, and recover the sanitized original by opaque id with integrity verification. The measured tool-schema reductions in reports 72–73 remain character counts, not token counts.

The overall certification therefore remains `NOT_CERTIFIED`. The next paid step is a fresh paired run using the same model, prompt, state, oracle, and explicitly recorded configuration hashes, with provider usage present for every valid execution.

## Reproduction

```powershell
& .\\.venv\\Scripts\\python.exe -m unittest tests.test_pie_domain_gateway -v
& .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p 'test_*.py'
```

No `codex exec` or other model runner was invoked for this acceptance report.
