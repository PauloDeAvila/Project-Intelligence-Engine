"""Regression tests for Ponytail-inspired offline token accounting."""
import json
import tempfile
import unittest
from pathlib import Path
from pie.telemetry.session_metrics import canonical_usage, analyze_cloud_results, analyze_file

class SessionMetricsTests(unittest.TestCase):
    def test_openai_cache_not_double_counted(self):
        u=canonical_usage({"usage":{"prompt_tokens":100,"completion_tokens":20,
                          "prompt_tokens_details":{"cached_tokens":60},
                          "completion_tokens_details":{"reasoning_tokens":5}}})
        self.assertEqual(u["total_tokens"],120)
        self.assertEqual(u["uncached_input_tokens"],40)
        self.assertEqual(u["cache_read_share"],0.6)

    def test_anthropic_cache_additive(self):
        u=canonical_usage({"input_tokens":10,"output_tokens":5,
                           "cache_read_input_tokens":80,
                           "cache_creation_input_tokens":20},"anthropic")
        self.assertEqual(u["total_tokens"],115)
        self.assertEqual(u["uncached_input_tokens"],10)

    def test_missing_is_not_free(self):
        self.assertIsNone(canonical_usage({"prompt_tokens":20},"openai")["total_tokens"])
        self.assertIsNone(canonical_usage({"input_tokens":5,"output_tokens":3},"anthropic")["total_tokens"])
        with self.assertRaises(ValueError):
            canonical_usage({"prompt_tokens":5,"completion_tokens":1,
                             "prompt_tokens_details":{"cached_tokens":7}},"openai")

    def test_paired_and_failures(self):
        results={"model":"gh/gpt-4o-mini","results":[
            {"repeat":0,"case":"a","mode":"baseline","ok":True,"seconds":1.0,
             "usage":{"prompt_tokens":100,"completion_tokens":10}},
            {"repeat":0,"case":"a","mode":"pie_rtk","ok":True,"seconds":1.2,
             "usage":{"prompt_tokens":65,"completion_tokens":10}},
            {"repeat":0,"case":"b","mode":"baseline","ok":False,"seconds":0.1,"status":503},
            {"repeat":0,"case":"b","mode":"pie_rtk","ok":True,"seconds":1.2,
             "usage":{"prompt_tokens":25,"completion_tokens":2}},
        ]}
        report=analyze_cloud_results(results)
        self.assertEqual(report["paired_count"],1)
        self.assertEqual(report["paired_saved_tokens"],35)
        self.assertEqual(report["modes"]["baseline"]["failed"],1)
        self.assertIsNone(report["modes"]["baseline"]["usage"]["cache_read_tokens"])
        self.assertIsNone(report["modes"]["baseline"]["certified"])
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/"results.json";b=Path(d)/"report.json"
            a.write_text(json.dumps(results),encoding="utf-8")
            analyze_file(a,b)
            self.assertEqual(json.loads(b.read_text())["paired_count"],1)

    def test_cost_only_with_rates_and_complete_cache(self):
        data={"model":"m","results":[{"repeat":0,"case":"a","mode":"baseline",
            "ok":True,"seconds":1,"usage":{"prompt_tokens":100,"completion_tokens":10,
            "prompt_tokens_details":{"cached_tokens":25}}}]}
        rates={"input_per_million":"1","output_per_million":"2",
               "cache_read_per_million":"0.5","cache_write_per_million":"0"}
        x=analyze_cloud_results(data,rates=rates)
        self.assertEqual(x["modes"]["baseline"]["estimated_cost_usd"],"0.0001075")
        self.assertEqual(x["modes"]["baseline"]["cost_source"],"explicit_rates_estimated_not_billed")

    def test_no_false_savings_or_bad_cells(self):
        payload={"model":"m","results":[
            {"repeat":0,"case":"a","mode":"baseline","ok":True,"seconds":1,
             "usage":{"prompt_tokens":10}},
            {"repeat":0,"case":"a","mode":"pie_rtk","ok":True,"seconds":2,
             "usage":{"prompt_tokens":2,"completion_tokens":1}},
        ]}
        r=analyze_cloud_results(payload)
        self.assertIsNone(r["paired_saved_tokens"])
        self.assertIsNone(r["paired_reduction_percent"])
        with self.assertRaises(ValueError):
            analyze_cloud_results({"model":"m","results":[payload["results"][0]]*2})
        with self.assertRaises(ValueError):
            analyze_cloud_results({"model":"m","results":[payload["results"][0]]},rates={"input_per_million":1})

if __name__ == "__main__":
    unittest.main()
