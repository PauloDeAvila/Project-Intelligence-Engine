"""Run validated material jobs inside Blender with bpy; no dynamic Python execution."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pie.blender.material_spec import fingerprint, load_spec


def _srgb_to_linear(component: int) -> float:
    c = component / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def apply_materials(spec: dict, bpy) -> dict:
    """Apply deterministic Principled BSDF materials to the current Blender file."""
    created = 0
    updated = 0
    for entry in spec["materials"]:
        material = bpy.data.materials.get(entry["name"])
        if material is None:
            material = bpy.data.materials.new(name=entry["name"])
            created += 1
        else:
            updated += 1
        material.use_nodes = True
        nodes = material.node_tree.nodes
        nodes.clear()
        output = nodes.new("ShaderNodeOutputMaterial")
        shader = nodes.new("ShaderNodeBsdfPrincipled")
        material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
        hexcolor = entry["base_color"][1:]
        rgb = tuple(_srgb_to_linear(int(hexcolor[i:i+2], 16)) for i in (0, 2, 4))
        shader.inputs["Base Color"].default_value = (*rgb, 1.0)
        shader.inputs["Metallic"].default_value = entry["metallic"]
        shader.inputs["Roughness"].default_value = entry["roughness"]
    return {"status": "success", "created": created, "updated": updated,
            "count": len(spec["materials"]), "fingerprint": fingerprint(spec)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Apply a validated Blender material job")
    parser.add_argument("spec", help="JSON job path")
    parser.add_argument("--output", required=True, help="Output .blend file; must not already exist")
    args = parser.parse_args(argv)
    output = Path(args.output).resolve()
    if output.suffix.lower() != ".blend" or output.exists():
        parser.error("output must be a new .blend file")
    spec = load_spec(args.spec)
    import bpy  # Only available in Blender's Python environment.
    result = apply_materials(spec, bpy)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    result["output"] = str(output)
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    import sys
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    raise SystemExit(main(arguments))
