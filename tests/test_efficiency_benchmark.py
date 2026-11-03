import unittest

from tools.benchmark_pie_efficiency import score, direct_calls


class EfficiencyBenchmarkContractTests(unittest.TestCase):
    def test_score_requires_exact_verified_locations(self):
        gold = [{"path": "a.py", "line": 10}, {"path": "b.py", "line": 20}]
        self.assertEqual(score({"definition": {"path": "a.py"}, "callers": gold}, gold)["recall"], 1.0)
        self.assertEqual(score({"definition": {"path": "a.py"}, "callers": [{"path": "a.py", "line": 10}]}, gold)["recall"], 0.5)

    def test_qualified_method_does_not_count_unrelated_get_calls(self):
        files = {"x.py": {"raw": b"value.get()\n", "bytes": 12, "sha256": ""}}
        self.assertEqual(direct_calls(files, "MeasurementCache.get"), [])

    def test_real_context_pack_shape_marks_qualified_definition_only(self):
        pack = {"definition": {"symbol": "MeasurementCache.get", "path": "cache.py"}, "callers": []}
        result = score(pack, [])
        self.assertIsNone(result["recall"])
        self.assertEqual(result["call_coverage"], "not_applicable_definition_only")


if __name__ == "__main__":
    unittest.main()
