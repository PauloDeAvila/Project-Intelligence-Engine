"""Validate the generated Blender observation and trigger PIE compaction offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pie.retrieval.output_pipeline import compact_output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    observation_text = args.observation.read_text(encoding="utf-8")
    observation = json.loads(observation_text)
    assert len(observation["objects"]) == spec["object_count"]
    assert len(observation["materials"]) == spec["material_count"]
    names = {item["name"] for item in observation["objects"]}
    material_names = {item["name"] for item in observation["materials"]}
    assert set(spec["oracle"]["required_object_names"]).issubset(names)
    assert set(spec["oracle"]["required_material_names"]).issubset(material_names)

    compacted = compact_output(args.root, observation_text, kind="api", max_chars=4000)
    assert compacted["state"] == "PARTIAL"
    assert compacted["source_chars"] > compacted["returned_chars"]
    assert compacted["sha256"] == hashlib.sha256(observation_text.encode("utf-8")).hexdigest()
    print(json.dumps({
        "status": "PASS",
        "fixture_verified": True,
        "objects": len(observation["objects"]),
        "materials": len(observation["materials"]),
        "compaction_state": compacted["state"],
        "source_chars": compacted["source_chars"],
        "returned_chars": compacted["returned_chars"],
        "sha256": compacted["sha256"],
        "model_sessions_started": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
