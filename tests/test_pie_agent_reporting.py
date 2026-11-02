"""Reporting regression including missing token usage and HTTP failures."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class ReportTests(unittest.TestCase):
    def test_missing_and_valid_usage_are_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            source=folder/"results.json"
            source.write_text(json.dumps({"results":[
                {"task":0,"mode":"pie","model":"qd/qfmodel","ok":True,"correct":True,"calls":2,
                 "prompt_tokens":300,"completion_tokens":40,"searches":1,
                 "model_ms":[100,110],"search_ms":[25]},
                {"task":0,"mode":"baseline","model":"qd/qfmodel","ok":False,"error":"HTTPError",
                 "error_detail":"HTTP Error 429"}]}))
            process=subprocess.run([sys.executable,"tools/pie_agent_report.py",
                "--input",str(source),"--out",str(folder/"output")],
                capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            report=json.loads((folder/"output"/"summary.json").read_text())
            self.assertEqual(report["attempts"],2)
            self.assertEqual(report["failures"],1)
            self.assertEqual(report["correct_completed"],1)
            self.assertEqual(report["prompt_tokens_reported"],300)
            import csv
            with (folder/"output"/"attempts.csv").open(newline="") as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),2)
            self.assertEqual(rows[0]["model_ms_total"],"210")
            self.assertEqual(rows[1]["prompt_tokens"],"")
            self.assertEqual(rows[1]["error"],"HTTPError")

if __name__=="__main__":
    unittest.main()
