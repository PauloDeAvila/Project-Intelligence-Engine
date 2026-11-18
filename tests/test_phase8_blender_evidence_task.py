from tools.phase8_blender_live_evidence_task import TASKS, _normalize_answer


def test_default_cube_task_matches_live_default_scene_contract():
    assert TASKS["default_cube"] == {
        "object_name": "Cube",
        "object_type": "MESH",
        "location": [0.0, 0.0, 0.0],
        "material_names": ["Material"],
    }


def test_blender_type_enum_normalization_preserves_exact_values():
    answer = {
        "object_name": "PIE_Large_Cube_00",
        "object_type": "mesh",
        "location": [0.0, 0.0, 0.0],
        "material_names": ["PIE_Large_Material_00"],
    }
    normalized = _normalize_answer(answer)
    assert normalized["object_type"] == "MESH"
    assert normalized["object_name"] == answer["object_name"]
    assert normalized["location"] == answer["location"]
