"""Run deterministic offline task oracles through the PIE scene-query contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_phase3_blender_query_scene import Client


def call_query(client: Client, identifier: int, *, prefix: str, fields: list[str],
               limit: int, offset: int) -> tuple[dict, float, int]:
    request = {"name": "pie_blender_query_scene", "arguments": {
        "query": "find_objects", "filters": {"name_prefix": prefix},
        "fields": fields, "limit": limit, "offset": offset,
    }}
    started = time.perf_counter()
    response = client.call(identifier, "tools/call", request)
    elapsed = (time.perf_counter() - started) * 1000
    payload = json.loads(response["result"]["content"][0]["text"])
    serialized = len(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    return payload, elapsed, serialized


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--uvx", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    spec = json.loads((root / "fixtures" / "phase3" / "blender" / "large_scene_spec.json").read_text(encoding="utf-8"))
    expected_objects = [spec["object_name_pattern"].format(index=index)
                        for index in range(spec["object_count"])]
    expected_materials = [spec["material_name_pattern"].format(index=index)
                          for index in range(spec["material_count"])]
    expected_location = [0.0, 0.0, 0.0]
    expected_b_names = expected_objects[:10]
    expected_b_materials = [
        [expected_materials[index // spec["objects_per_material"]]]
        for index in range(10)
    ]
    store = root / ".pie-task-simulation-store"
    upstream = [str(args.uvx), "mcp-for-blender", "--port", "9877"]
    command = [str(args.python), "-m", "pie.gateway.domain", "serve", "--domain", "blender",
               "--workspace", str(root), "--store", str(store), "--max-chars", "2400", "--", *upstream]
    import os
    process = subprocess.Popen(command, cwd=root, env=dict(os.environ, PIE_GLOBAL_STORAGE_ROOT=str(store)),
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", bufsize=1)
    client = Client(process)
    try:
        init = client.call(1, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                               "clientInfo": {"name": "pie-task-simulation", "version": "1"}})
        client.notify("notifications/initialized")
        tools = client.call(2, "tools/list", {})
        discovered = next(item for item in tools["result"]["tools"] if item["name"] == "pie_blender_query_scene")
        task_a, a_ms, a_chars = call_query(client, 3, prefix="PIE_Large_Cube_00",
                                           fields=["name", "type", "location", "material_names"], limit=1, offset=0)
        task_b, b_ms, b_chars = call_query(client, 4, prefix="PIE_Large_Cube_0",
                                           fields=["name", "material_count", "material_names"], limit=20, offset=0)
        pages = []
        c_ms = 0.0
        c_chars = 0
        for index, offset in enumerate((0, 20, 40, 60), start=5):
            page, elapsed, chars = call_query(client, index, prefix="PIE_Large_Cube_",
                                               fields=["name", "type", "material_count"], limit=20, offset=offset)
            pages.append(page)
            c_ms += elapsed
            c_chars += chars
        a_items = task_a["items"]
        b_items = task_b["items"]
        c_items = [item for page in pages for item in page["items"]]
        c_names = [item["name"] for item in c_items]
        a_oracle = (
            len(a_items) == 1
            and a_items[0] == {"name": expected_objects[0], "type": "MESH",
                               "location": expected_location,
                               "material_names": [expected_materials[0]]}
        )
        b_oracle = (
            [item["name"] for item in b_items] == expected_b_names
            and [item.get("material_names") for item in b_items] == expected_b_materials
            and [item.get("material_count") for item in b_items] == [1] * 10
        )
        c_oracle = (
            c_names == expected_objects
            and [item.get("type") for item in c_items] == ["MESH"] * spec["object_count"]
            and [item.get("material_count") for item in c_items] == [1] * spec["object_count"]
            and [page["total"] for page in pages] == [spec["object_count"]] * 4
            and [page["offset"] for page in pages] == [0, 20, 40, 60]
            and [page["next_offset"] for page in pages] == [20, 40, 60, None]
        )
        result = {
            "schema": "pie-phase3-blender-selective-task-simulation-v1",
            "status": "PASS" if "result" in init else "BLOCKED",
            "experiment_arm": "optimized_only",
            "ab_comparison": "NOT_RUN",
            "model_sessions": 0, "quota_consumed": False,
            "contract": {"tool": discovered["name"], "input_schema": discovered["inputSchema"], "output_schema": discovered.get("outputSchema")},
            "tasks": {
                "A_location": {"query_calls": 1, "latency_ms": round(a_ms, 3), "response_chars": a_chars,
                                "oracle_pass": a_oracle,
                                "expected": {"name": expected_objects[0], "type": "MESH",
                                             "location": expected_location, "material_names": [expected_materials[0]]},
                                "result": task_a},
                "B_filtering": {"query_calls": 1, "latency_ms": round(b_ms, 3), "response_chars": b_chars,
                                 "oracle_pass": b_oracle,
                                 "expected_names": expected_b_names,
                                 "expected_material_names": expected_b_materials,
                                 "result": task_b},
                "C_inventory": {"query_calls": 4, "latency_ms": round(c_ms, 3), "response_chars": c_chars,
                                "oracle_pass": c_oracle,
                                "expected_names": expected_objects,
                                "expected_object_count": spec["object_count"],
                                "expected_material_count": spec["material_count"],
                                "page_counts": [len(page["items"]) for page in pages],
                                "result_pages": pages},
            },
            "upstream_calls_per_query": 1,
            "note": "Offline task/oracle validation only; response characters are not provider tokens.",
        }
    finally:
        client.close()
    result["status"] = "PASS" if all(item["oracle_pass"] for item in result["tasks"].values()) else "BLOCKED"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
