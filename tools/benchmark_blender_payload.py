"""Deterministic payload-only benchmark for the PIE Blender MCP bridge.

This is NOT a Blender/MCP runtime benchmark, model token measurement or
semantic-equivalence proof. It exercises the same compaction function with
a synthetic, verbose read-only scene response.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pie.integrations.blender_mcp_bridge import SnapshotStore, compact_observation


def measure(objects: int = 1000, max_chars: int = 2400) -> dict:
    if type(objects) is not int or not 1 <= objects <= 100000:
        raise ValueError("objects must be an integer in 1..100000")
    source = json.dumps({
        "scene": "PIE_SYNTHETIC_BENCH",
        "objects": [{
            "name": f"Object_{i:05d}", "type": "MESH",
            "location": [float(i), 1.25, 2.5],
            "materials": ["SyntheticMetal", "SyntheticGlass"],
        } for i in range(objects)],
    }, ensure_ascii=False)
    message = {"jsonrpc": "2.0", "id": 1,
               "result": {"content": [{"type": "text", "text": source}]}}
    raw = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    store = SnapshotStore()
    after = compact_observation(message, "get_scene_info", store, max_chars)
    delivered = json.dumps(after, ensure_ascii=False, separators=(",", ":"))
    payload = after["result"]["content"][0]["text"]
    compact = json.loads(payload) if len(source) > max_chars and len(source) <= 2_000_000 else {}
    exact = False
    if compact.get("response_id"):
        ref = compact["response_id"]
        chunks = []
        start = 0
        while start < len(source):
            reply = store.expand({"response_id": ref, "start": start, "max_chars": 16000})
            body = json.loads(reply["content"][0]["text"])
            chunks.append(body["text"])
            start = body["end"]
        exact = "".join(chunks) == source
    return {
        "scenario": "synthetic_verbose_scene_read_only",
        "objects": objects,
        "max_chars": max_chars,
        "raw_response_chars": len(raw),
        "delivered_response_chars": len(delivered),
        "response_character_reduction_percent": round(100 * (1 - len(delivered) / len(raw)), 2),
        "first_response_state": compact.get("status", "PASSTHROUGH"),
        "full_response_recovered_exactly": exact,
        "measured_model_tokens": None,
        "measured_blender_runtime_ms": None,
        "semantic_task_correctness": "not_tested",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--objects", type=int, default=1000)
    parser.add_argument("--max-chars", type=int, default=2400)
    args = parser.parse_args(argv)
    print(json.dumps(measure(args.objects, args.max_chars), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
