#!/usr/bin/env python3
"""Re-score existing PIE cloud benchmark results entirely offline, without API calls."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from pie.telemetry.session_metrics import analyze_file, analyze_codex_file

def main(argv=None):
    p=argparse.ArgumentParser(description="Ponytail-inspired PIE token metrics from saved benchmark results (offline)")
    p.add_argument("results",type=Path,help="Existing results.json from PIE benchmark")
    p.add_argument("--out",type=Path,default=Path("benchmark-results/session-metrics.json"))
    p.add_argument("--provider",choices=("openai","anthropic"),default="openai")
    p.add_argument("--codex-jsonl",action="store_true",help="Read Codex turn.completed usage; no prompts retained")
    p.add_argument("--input-per-million")
    p.add_argument("--output-per-million")
    p.add_argument("--cache-read-per-million")
    p.add_argument("--cache-write-per-million")
    a=p.parse_args(argv)
    inputs=(a.input_per_million,a.output_per_million,a.cache_read_per_million,a.cache_write_per_million)
    if any(x is not None for x in inputs) and not all(x is not None for x in inputs):
        p.error("all four explicit pricing rates must be supplied together")
    rates=dict(zip(("input_per_million","output_per_million","cache_read_per_million","cache_write_per_million"),inputs)) if all(x is not None for x in inputs) else None
    if a.codex_jsonl:
        if rates is not None: p.error("Codex JSONL mode does not infer billing prices")
        report=analyze_codex_file(a.results)
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({"schema":report["schema"],"turns":report["turns_completed"],"usage":report["usage"],"output":str(a.out)},ensure_ascii=False))
        return 0
    report=analyze_file(a.results,a.out,provider=a.provider,rates=rates)
    print(json.dumps({"schema":report["schema"],"model":report["model"],
        "paired_count":report["paired_count"],
        "saved_tokens":report["paired_saved_tokens"],
        "reduction_percent":report["paired_reduction_percent"],
        "modes":report["modes"],
        "output":str(a.out)},ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
