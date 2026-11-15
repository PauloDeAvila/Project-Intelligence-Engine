"""Create the deterministic Phase 3 Blender fixture in a disposable .blend file.

Run with Blender's bundled Python, for example:
  blender --background --python tools/generate_phase3_blender_fixture.py -- \
    --spec fixtures/phase3/blender/large_scene_spec.json \
    --blend .tmp/phase3-large.blend \
    --observation .tmp/phase3-large-observation.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--observation", required=True, type=Path)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def main() -> None:
    args = _arguments()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    collection = bpy.data.collections.new("PIE_Phase3_Large_Fixture")
    bpy.context.scene.collection.children.link(collection)

    materials = []
    for index in range(spec["material_count"]):
        source = spec["materials"][index % len(spec["materials"])]
        material = bpy.data.materials.new(spec["material_name_pattern"].format(index=index))
        material.diffuse_color = (0.15 + (index % 8) * 0.08, 0.25, 0.45, 1.0)
        material.metallic = source["metallic"]
        material.roughness = source["roughness"]
        materials.append(material)

    for index in range(spec["object_count"]):
        bpy.ops.mesh.primitive_cube_add(location=(index % 8, index // 8, 0))
        obj = bpy.context.object
        obj.name = spec["object_name_pattern"].format(index=index)
        obj.data.name = f"PIE_Large_Mesh_{index:02d}"
        obj.data.materials.append(materials[index // spec["objects_per_material"]])
        for collection_ref in tuple(obj.users_collection):
            collection_ref.objects.unlink(obj)
        collection.objects.link(obj)

    args.blend.parent.mkdir(parents=True, exist_ok=True)
    args.observation.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.blend.resolve()))

    observation = {
        "schema": "pie-phase3-blender-observation-v1",
        "scene": bpy.context.scene.name,
        "objects": [
            {
                "name": obj.name,
                "type": obj.type,
                "location": [round(value, 4) for value in obj.location],
                "materials": [slot.material.name for slot in obj.material_slots if slot.material],
            }
            for obj in sorted(collection.objects, key=lambda item: item.name)
        ],
        "materials": [
            {
                "name": material.name,
                "metallic": material.metallic,
                "roughness": material.roughness,
            }
            for material in sorted(materials, key=lambda item: item.name)
        ],
    }
    args.observation.write_text(json.dumps(observation, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "blend": str(args.blend.resolve()),
        "observation": str(args.observation.resolve()),
        "object_count": len(observation["objects"]),
        "material_count": len(observation["materials"]),
    }))


if __name__ == "__main__":
    main()
