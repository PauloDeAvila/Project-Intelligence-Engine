"""Runtime evidence is compared with a separately specified reference."""
import unittest
import tempfile
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from cloud_pie_benchmark import LAB, ANSWER_KEYS
from pie_runtime_verifier import observe_case

class RuntimeOracleTests(unittest.TestCase):
    def test_all_counterfactual_scenarios_execute(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name,source in LAB.items():
                target=root/name
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_text(source,encoding="utf-8")
            for case,expected in ANSWER_KEYS.items():
                with self.subTest(case=case):
                    self.assertEqual(observe_case(root,case),expected)
    def test_unknown_scenario_fails_closed(self):
        with self.assertRaises(ValueError):
            observe_case(Path("."),"unknown_scenario")

if __name__=="__main__":
    unittest.main()
