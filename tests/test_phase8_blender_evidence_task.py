from tools.phase8_blender_live_evidence_task import _normalize_answer


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
