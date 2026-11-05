"""Conservative unittest report compaction, adapted from Caveman's testreport concept.

Reads actual unittest -v output; only collapses known success rows. Tracebacks,
FAIL/ERROR, malformed formats and missing summaries remain verbatim. Output is
advisory and the PIE gateway remains the owner of sanitized original recovery.
"""
from __future__ import annotations
import re

_PASS = re.compile(r"^(test_[A-Za-z0-9_]+) \(([^\n()]*)\) \.\.\. ok$",re.I)
_SUMMARY = re.compile(r"^Ran ([0-9]+) tests? in ([0-9.]+)s$")
_NOISE = {"", "----------------------------------------------------------------------", "OK"}
_BAD = re.compile(r"\b(?:FAIL|ERROR|Traceback|AssertionError|FAILED|skipped|expected failure|unexpected success)\b",re.I)

def compact_unittest_success(text: str) -> dict:
    if not isinstance(text,str):
        raise TypeError("test report must be text")
    lines=text.splitlines()
    if _BAD.search(text):
        return {"text":text,"state":"PASSTHROUGH","reason":"failures_or_unknown_outcomes","covered":0}
    cases=[]
    run_count=0
    ran_total=0
    for line in lines:
        line=line.strip()
        if not line or line == "----------------------------------------------------------------------" or line == "OK":
            continue
        match=_PASS.fullmatch(line)
        if match:
            cases.append((match.group(1),match.group(2)))
            continue
        summary=_SUMMARY.fullmatch(line)
        if summary:
            run_count+=1
            ran_total+=int(summary.group(1))
            continue
        return {"text":text,"state":"PASSTHROUGH","reason":"unknown_format","covered":0}
    if run_count != 1 or len(cases)!=ran_total or not cases or "OK" not in lines:
        return {"text":text,"state":"PASSTHROUGH","reason":"incomplete_report","covered":0}
    # Fully describe all successes, do not guess which test applies to the question.
    label=", ".join(name for name,_ in cases)
    result=f"UNITTEST OK: {ran_total} passed; tests: {label}"
    if len(result)>=len(text):
        return {"text":text,"state":"PASSTHROUGH","reason":"not_smaller","covered":len(cases)}
    return {"text":result,"state":"COMPLETE","reason":"validated_success_summary","covered":len(cases)}
