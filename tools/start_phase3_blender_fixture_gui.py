"""Enable the installed Blender MCP addon and serve a disposable fixture."""
import bpy

bpy.ops.preferences.addon_enable(module="blender_mcp")
bpy.context.scene.blendermcp_auto_start_server = False
bpy.context.scene.blendermcp_port = 9877
result = bpy.ops.blendermcp.start_server()
print(f"PIE_PHASE3_GUI_BLENDER={result} port=9877 file={bpy.data.filepath}", flush=True)
