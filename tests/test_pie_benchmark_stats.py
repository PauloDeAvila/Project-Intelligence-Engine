import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from pie_benchmark_stats import paired_summary

class PairedStatsTests(unittest.TestCase):
    def test_matching_ignores_unpaired_results(self):
        data={"results":[
            {"repeat":0,"case":"A","mode":"baseline","ok":True,"seconds":2,
             "usage":{"prompt_tokens":100}},
            {"repeat":0,"case":"A","mode":"pie","ok":True,"seconds":1,
             "usage":{"prompt_tokens":30}},
            {"repeat":1,"case":"A","mode":"baseline","ok":True,"seconds":5,
             "usage":{"prompt_tokens":100}}
        ]}
        result=paired_summary(data,"baseline","pie")
        self.assertEqual(result["pairs"],1)
        self.assertEqual(result["median_paired_latency_delta_s"],-1)
        self.assertEqual(result["total_measured_prompt_tokens_saved"],70)
    def test_deterministic_bootstrap(self):
        data={"results":[]}
        for i in range(6):
            data["results"] += [
                {"repeat":i,"case":"A","mode":"baseline","ok":True,"seconds":2},
                {"repeat":i,"case":"A","mode":"pie","ok":True,"seconds":1.5+i*.01}
            ]
        a=paired_summary(data,"baseline","pie")
        b=paired_summary(data,"baseline","pie")
        self.assertEqual(a["median_paired_delta_95pct_bootstrap_ci_s"],b["median_paired_delta_95pct_bootstrap_ci_s"])
        self.assertEqual(a["fraction_candidate_faster"],1.0)
if __name__=="__main__":unittest.main()
