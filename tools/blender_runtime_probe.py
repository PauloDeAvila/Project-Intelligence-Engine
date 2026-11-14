"""Real Blender bpy smoke: confirm PIE node snapshot and material delta on an ephemeral scene."""
from __future__ import annotations
import contextlib,io,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))

def main()->int:
    try:
        import bpy
        from pie.integrations.blender_delta import MARKER,SceneDeltaCache,snapshot_code
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.mesh.primitive_cube_add()
        obj=bpy.context.active_object
        assert obj is not None and obj.type=="MESH"
        mat=bpy.data.materials.new("PIE_Roughness_Test")
        mat.use_nodes=True
        obj.data.materials.append(mat)
        node=next(n for n in mat.node_tree.nodes if n.bl_idname=="ShaderNodeBsdfPrincipled")
        rough=node.inputs.get("Roughness")
        assert rough is not None
        def snap():
            buffer=io.StringIO()
            with contextlib.redirect_stdout(buffer):
                exec(snapshot_code("all"),{"__name__":"__main__"})
            text=buffer.getvalue().strip()
            assert text.startswith(MARKER),"PIE snapshot marker absent"
            return json.loads(text[len(MARKER):])
        rough.default_value=0.35
        before=snap();cache=SceneDeltaCache()
        first=cache.observe(before,max_chars=16000)
        same=cache.observe(before,max_chars=16000)
        rough.default_value=0.28
        delta=cache.observe(snap(),max_chars=16000)
        body=json.dumps(delta,separators=(",",":"),ensure_ascii=False)
        ok=(first["state"]=="INITIAL" and same["state"]=="UNCHANGED"
            and delta["state"]=="DELTA" and
            "Roughness" in body and "0.35" in body and "0.28" in body)
        result={"schema":"pie-real-blender-bpy-probe-v1",
                "state":"PASS" if ok else "FAIL","blender_version":bpy.app.version_string,
                "initial":first["state"],"unchanged":same["state"],"delta":delta["state"],
                "material_delta_found":"Roughness" in body,
                "source":"actual_blender_bpy_not_mock",
                "note":"Headless bpy only, not Codex/GPU GUI integration"}
    except Exception as ex:
        result={"schema":"pie-real-blender-bpy-probe-v1","state":"FAIL",
                "error_type":type(ex).__name__,"source":"actual_blender_bpy_not_mock"}
    print("PIE_BLENDER_LIVE_REPORT="+json.dumps(result,separators=(",",":")),flush=True)
    return 0 if result["state"]=="PASS" else 1
if __name__=="__main__":raise SystemExit(main())
