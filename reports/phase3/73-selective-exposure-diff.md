# PIE Phase 3 — selective capability exposure

The gateway now supports an opt-in `--expose-tool` allowlist. The default gateway behavior is
unchanged, preserving all upstream tools and recovery capabilities. A task-specific profile can
use the option to advertise only the tools needed by a deterministic scenario plus explicit
recovery tools.

Offline probe results:

| Domain | Profile | Tools | Serialized list | Descriptions | Schemas |
|---|---|---:|---:|---:|---:|
| Blender | baseline upstream | 10 | 18,750 | 11,039 | 5,613 |
| Blender | optimized default | 13 | 20,045 | 11,528 | 6,224 |
| Blender | optimized selective | 4 | 3,792 | 2,106 | 1,104 |
| Web | baseline upstream | 25 | 21,177 | 1,979 | 14,967 |
| Web | optimized default | 26 | 21,583 | 2,103 | 15,183 |
| Web | optimized selective | 3 | 1,738 | 223 | 1,114 |

Selective Blender exposed `get_scene_info`, `execute_blender_code`, `pie_blender_expand` and
`pie_gateway_output_get`. Selective Web exposed `browser_navigate`, `browser_snapshot` and
`pie_gateway_output_get`.

This reduces the serialized optimized tool list by 16,253 characters for Blender and 19,845 for
Web relative to the default optimized gateway. These are structural measurements, not token
measurements; they do not predict provider savings directly.

Safety checks passed offline:

- Hidden tools are not advertised.
- Calls to hidden tools fail closed with `PIE_TOOL_NOT_EXPOSED` and are not forwarded upstream.
- Normal MCP initialize/tools/list/tools/call framing remains valid.
- Recovery remains advertised when explicitly included.
- The default gateway remains unchanged when `--expose-tool` is omitted.
