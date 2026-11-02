"""Regression checks for the real-repository discovery laboratory."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from pie_real_repo_lab import normalize_navigation_answer, benchmark_tasks

class RealRepoLabTests(unittest.TestCase):
    def test_path_line_reference_normalized_without_changing_symbol(self):
        self.assertEqual(
            normalize_navigation_answer({"path":"rich/live.py:278","symbol":"Live.process_renderables"}),
            {"path":"rich/live.py","symbol":"Live.process_renderables"})
        self.assertEqual(
            normalize_navigation_answer({"path":"### rich/segment.py:520-534","symbol":"Segment.align_middle"}),
            {"path":"rich/segment.py","symbol":"Segment.align_middle"})
    def test_invalid_answer_cannot_be_scored(self):
        self.assertEqual(normalize_navigation_answer({"path":4,"symbol":"ok"}),{})
        self.assertEqual(normalize_navigation_answer(None),{})
    def test_generated_tasks_are_seeded_and_deduplicated_by_file(self):
        rows=[{"path":f"rich/m{i}.py","symbol":f"f{i}","sentence":"This is a detailed implementation description."} for i in range(20)]
        a=benchmark_tasks(rows,12,412)
        b=benchmark_tasks(rows,12,412)
        self.assertEqual(a,b)
        self.assertEqual(len({t["oracle"]["path"] for t in a}),12)
    def test_not_enough_real_modules_fails(self):
        rows=[{"path":"rich/a.py","symbol":"a","sentence":"A lengthy description of the function."}]
        with self.assertRaises(RuntimeError):benchmark_tasks(rows,3,123)

if __name__=="__main__":unittest.main()
