# Codex → PIE → Blender: isolated route probe

Status: `ROUTE_AND_TASK_PASS_STRICT_ISOLATION`.

The temporary Codex home exposed exactly one MCP server: `pie-blender-optimized`.
The Codex completed `get_addon_status` and `get_scene_info`; no `cua_repl`,
`node_repl`, original Blender server or other MCP server was observed.

The independent Blender oracle passed: Blender 5.3.0, addon 2.0, protocol 16,
three scene objects, one mesh, one light and one camera. The scene was unchanged.

Provider usage was available: 72,491 input tokens (54,144 cached), 500 output
tokens, 237 reasoning tokens and 72,991 total tokens.

The temporary configuration SHA-256 is
`DADC8351B850C17A94E93C866EC9D93634C42AB4FA21819A8F27846E05A55B72`; the
user's original Codex configuration was not modified.

This proves strict routing for the probe, not token-savings certification. The
production executor still needs to materialize this isolated profile automatically.
