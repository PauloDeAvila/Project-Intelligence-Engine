# Live Blender gateway probe — 2026-11-16

## Result

`PASS_EXTERNAL_CONTROLLED_READ_ONLY`.

The current-root PIE gateway successfully routed real MCP traffic to Blender
5.3.0 through the installed addon.

## Evidence

- Endpoint: `127.0.0.1:9876`.
- `initialize`: PASS.
- `tools/list`: PASS, 15 tools.
- `get_addon_status`: PASS.
- Addon version: `2.0`.
- Protocol: `16` expected `16`.
- `get_scene_info`: PASS, no MCP error, 284 characters returned.
- Gateway process returned code `0`.

The isolated process used Blender `--factory-startup`; the returned scene was
the default `Cube`, `Light`, and `Camera`. No user scene was loaded or changed.

## Port correction

The addon and the configured `mcp-for-blender` route use port `9876` by
default. The earlier diagnostic checked `9877`, which was not the active
configured endpoint. That earlier report remains as historical evidence of the
pre-start state, while this report is the authoritative live probe.

## Scope limitation

This proves the real Blender gateway path and read-only calls. It does not yet
prove the large-scene fixture, selective-query payload reduction, or a model
token A/B benchmark against Blender.
