"""Scenario contracts must read the same Blender fields as the independent oracle."""
from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ScenarioContractTests(unittest.TestCase):
    def test_blender_prompt_reads_principled_node_values(self):
        scenario = json.loads(
            (ROOT / "benchmarks/phase3/blender-certification-scenario.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("BSDF_PRINCIPLED", scenario["prompt"])
        self.assertIn("node.inputs['Roughness'].default_value", scenario["prompt"])
        self.assertIn("node.inputs['Metallic'].default_value", scenario["prompt"])
        self.assertNotIn("'roughness': mat.roughness", scenario["prompt"])
        self.assertNotIn("'metallic': mat.metallic", scenario["prompt"])


if __name__ == "__main__":
    unittest.main()
