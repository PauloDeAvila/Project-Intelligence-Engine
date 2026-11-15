"""Tests for the production PIE exact-object router: no model or Blender needed."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pie.integrations.blender_routing import (
    EXACT_READ_TOOLS, ExactRouteError, route_exact_object,
)


class ExactObjectRoutingTests(unittest.TestCase):
    def test_all_fixture_names_routable_by_exact_index(self):
        candidates = [f"PIE_Large_Cube_{i:02d}" for i in range(64)]
        tools = [
            {"name": "get_scene_info"},
            {"name": "pie_blender_get_object", "inputSchema": {"type": "object"}},
        ]
        for i, requested in enumerate(candidates):
            with self.subTest(i=i):
                chosen = route_exact_object(tools, candidates, requested)
                self.assertEqual(chosen.tool_index, 1)
                self.assertEqual(chosen.target_index, i)
                self.assertEqual(chosen.object_name, requested)
                self.assertEqual(chosen.tool_name, "pie_blender_get_object")
                self.assertEqual(chosen.strategy, "DETERMINISTIC_EXACT_MATCH_NO_MODEL")

    def test_tool_order_and_target_order_are_not_assumed(self):
        tools = [{"name": "execute_blender_code"}, {"name": "get_scene_info"}]
        names = ["Cube_63", "Cube_00", "Cube_13"]
        choice = route_exact_object(tools, names, "Cube_13")
        self.assertEqual((choice.tool_index, choice.target_index), (0, 2))
        self.assertEqual(choice.tool_name, "execute_blender_code")

    def test_pie_exact_tool_preferred_over_generic_code(self):
        tools = [{"name": "execute_blender_code"},
                 {"name": "pie_blender_get_object"}]
        self.assertEqual(
            route_exact_object(tools, ["cube"], "cube").tool_name,
            "pie_blender_get_object")

    def test_never_routes_to_unsafe_or_similarly_named_tools(self):
        for tools in (
            [{"name": "delete_object"}],
            [{"name": "execute_blender_code_unsafe"}],
            [{"name": "pie_blender_get_object_debug"}],
            [{"name": "get_scene_info"}],
        ):
            with self.subTest(tools=tools), self.assertRaises(ExactRouteError):
                route_exact_object(tools, ["Cube"], "Cube")

    def test_fail_closed_if_name_missing_ambiguous_or_malformed(self):
        cases = [
            (["Cube"], "Cube "),
            (["Cube", "Cube"], "Cube"),
            (["Cube"], ""),
            (["Cube"], "C" * 129),
            (["Cube"], "Cube\x00"),
            (["Cube", ""], "Cube"),
            (["Cube", 8], "Cube"),
            ([], "Cube"),
        ]
        for candidates, requested in cases:
            with self.subTest(candidates=candidates, requested=requested):
                with self.assertRaises(ExactRouteError):
                    route_exact_object([{"name": "pie_blender_get_object"}],
                                       candidates, requested)

    def test_reject_malformed_or_duplicate_catalog(self):
        for tools in (
            [{"name": "execute_blender_code"}, {"name": "execute_blender_code"}],
            [{"name": 99}], [{}], [], ["not a schema"],
        ):
            with self.subTest(tools=tools), self.assertRaises(ExactRouteError):
                route_exact_object(tools, ["Cube"], "Cube")


if __name__ == "__main__":
    unittest.main()
