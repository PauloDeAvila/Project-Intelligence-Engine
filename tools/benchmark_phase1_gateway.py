"""Deterministic, offline Phase-1 gateway reduction AND recovery gate.

A functional fixture, not a provider token benchmark or proof of task quality.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from pie.gateway.policy import reduce_text
from pie.retrieval.output_pipeline import recover_output, _redact


def measure(*, max_chars: int = 1200) -> dict:
    if not 800 <= max_chars <= 64000:
        raise ValueError("Invalid budget")
    with tempfile.TemporaryDirectory(prefix="pie-phase1-fixture-") as tmp:
        root=Path(tmp)/"workspace"
        root.mkdir()
        store=Path(tmp)/"store"
        (root/"pyproject.toml").write_text("[project]\nname='fixture'\n",encoding="utf8")
        old=os.environ.get("PIE_GLOBAL_STORAGE_ROOT")
        os.environ["PIE_GLOBAL_STORAGE_ROOT"]=str(store)
        try:
            content=("PASS unit_case_1\n"*850+
                     "FAILED test_material: expected 24 links, found 23\n"+
                     "Authorization: Bearer example-sensitive-placeholder\n")
            result=reduce_text(root,content,surface="terminal",tool="pytest",
                               kind="test",max_chars=max_chars,exit_code=1)
            restored=recover_output(root,result["output_id"])
            sanitized=_redact(content)
            model_payload=json.dumps(result,separators=(",",":"),ensure_ascii=False)
            source_chars=len(sanitized)
            model_chars=len(model_payload)
            exact=(restored["text"]==sanitized and
                   sha256(restored["text"].encode()).hexdigest()==restored["sha256"])
            return {
                "fixture":"repetitive_test_log_with_failure_and_redaction",
                "functional_gate":"PASS" if exact and "FAILED" in result["text"] else "FAIL",
                "source_chars":source_chars,
                "model_facing_chars":model_chars,
                "saved_chars":source_chars-model_chars,
                "character_reduction_percent":round(100*(1-model_chars/source_chars),3),
                "sanitized_source_recovered_exactly":exact,
                "exit_code_preserved":result["exit_code"]==1,
                "secret_placeholder_not_returned":("example-sensitive-placeholder"
                                                     not in model_payload+restored["text"]),
                "provider_prompt_tokens":None,
                "provider_completion_tokens":None,
                "provider_tokens_measured":False,
                "claim":"fixture_character_savings_not_real_model_token_savings",
            }
        finally:
            if old is None:
                os.environ.pop("PIE_GLOBAL_STORAGE_ROOT",None)
            else:
                os.environ["PIE_GLOBAL_STORAGE_ROOT"]=old


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description="Offline PIE Phase 1 functional reduction gate")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--max-chars",type=int,default=1200)
    args=parser.parse_args(argv)
    result=measure(max_chars=args.max_chars)
    if args.output:
        args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if (result["functional_gate"]=="PASS" and
                 result["exit_code_preserved"] and
                 result["secret_placeholder_not_returned"] and
                 result["saved_chars"]>0) else 1


if __name__=="__main__":
    raise SystemExit(main())
