# PIE Phase 3 — structural overhead diff

Measured offline by sending MCP `initialize` and `tools/list` directly to the original
upstreams and to the PIE gateways. No Codex model process or quota was used.

| Domain | Arm | Tools | Serialized list | Descriptions | Input schemas |
|---|---|---:|---:|---:|---:|
| Blender | baseline | 10 | 18,750 chars | 11,039 | 5,613 |
| Blender | optimized | 13 | 20,045 chars | 11,528 | 6,224 |
| Web | baseline | 25 | 21,177 chars | 1,979 | 14,967 |
| Web | optimized | 26 | 21,583 chars | 2,103 | 15,183 |

## Measured overhead

- Blender adds 3 advertised tools and 1,295 serialized characters: `pie_blender_expand`,
  `pie_blender_scene_delta` and `pie_gateway_output_get`.
- Web adds 1 advertised tool and 406 serialized characters: `pie_gateway_output_get`.
- These are structural differences, not token measurements. They establish a concrete overhead
  source but do not justify mapping characters directly to the provider's 52,402-token Blender
  delta.

## Relation to the valid A/B pairs

The A/B lifecycle/SQLite evidence showed no compaction: Blender `359 → 359` characters and Web
`824 → 824`, both `PASSTHROUGH`. Therefore the additional recovery/expansion schemas were paid
in the optimized context while no response reduction benefit was realized.

The next safe optimization is selective capability exposure for task profiles, with recovery
tools retained whenever a scenario can produce a compacted response. This requires an offline
contract test before any real benchmark.
