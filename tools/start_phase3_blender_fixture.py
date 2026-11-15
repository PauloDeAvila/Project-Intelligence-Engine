"""Start MCP for Blender on an isolated port for a disposable fixture."""
import bpy

bpy.context.scene.blendermcp_auto_start_server = False
bpy.context.scene.blendermcp_port = 9877
result = bpy.ops.blendermcp.start_server()
print(f"PIE_PHASE3_ISOLATED_BLENDER={result} port=9877 file={bpy.data.filepath}")
