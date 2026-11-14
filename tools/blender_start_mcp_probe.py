"""Start the installed Blender MCP addon for a controlled local probe."""
from __future__ import annotations

import json
import os
from pathlib import Path

import bpy


def main() -> None:
    marker = Path(os.environ.get("PIE_BLENDER_PROBE_MARKER", "pie-blender-probe.json"))
    result = {"addon_enabled": False, "server_started": False}
    try:
        bpy.ops.preferences.addon_enable(module="blender_mcp")
        result["addon_enabled"] = "blender_mcp" in bpy.context.preferences.addons
        result["operator_available"] = hasattr(bpy.ops, "blendermcp")
        if result["operator_available"]:
            result["operator_result"] = str(bpy.ops.blendermcp.start_server())
            result["server_started"] = bool(
                getattr(getattr(bpy.types, "blendermcp_server", None), "running", False)
            )
    except Exception as exc:  # pragma: no cover - executed inside Blender
        result["error"] = type(exc).__name__ + ": " + str(exc)[:300]
    marker.write_text(json.dumps(result), encoding="utf-8")


main()
