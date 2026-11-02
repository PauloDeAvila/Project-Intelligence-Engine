"""Executable code-edit benchmark: model calls and tests run in separate CI jobs.

Generated code is never executed in the credential-bearing job.
"""
from __future__ import annotations
import argparse
import ast
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from pie.indexing.indexer import index_project
from pie.retrieval.intelligence import smart_context

SOURCE = """import re
import unicodedata

def slugify(text):
    # Convert human titles to safe slugs.
    return text.lower().replace(" ", "-")

def unique_in_order(items):
    # Preserve first occurrence of even unhashable values.
    return list(set(items))

def backoff(base, attempt, cap):
    # Retry with capped exponential delay, attempt starts at zero.
    return base * attempt

def apply_ledger(balance, operations):
    # Do not allow any intermediate account overdraft.
    return balance + sum(operations)
"""
TASKS = [
    ("slugify","Convert accented Unicode text to lowercase ASCII; replace nonalphanumeric runs with single hyphens; remove outer hyphens; reject empty output with ValueError.",
     "self.assertEqual(f(' Café com LEITE! '),'cafe-com-leite'); self.assertRaises(ValueError,f,'!!!')"),
    ("unique_in_order","Deduplicate preserving first-occurrence order and support unhashable dicts/lists through equality.",
     "self.assertEqual(f([3,2,3,1,2]),[3,2,1]); self.assertEqual(f([{'a':1},{'a':1}]),[{'a':1}])"),
    ("backoff","Return min(cap, base * (2 ** attempt)) with zero-based attempt and reject negative inputs with ValueError.",
     "self.assertEqual(f(.5,0,9),.5); self.assertEqual(f(.5,3,9),4); self.assertRaises(ValueError,f,1,-1,9)"),
    ("apply_ledger","Process signed operations in order; reject negative initial balance or any negative intermediate result with ValueError.",
     "self.assertEqual(f(10,[-5,7,-2]),10); self.assertRaises(ValueError,f,5,[-10,20])"),
]

def generate(destination,model):
    base=os.environ["PIE_API_BASE_URL"].rstrip("/")
    key=os.environ["PIE_API_KEY"]
    if not base.startswith("https://"):
        raise ValueError("HTTPS required")
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        (root/"service.py").write_text(SOURCE,encoding="utf8")
        if index_project(root)["index_state"]!="CURRENT":
            raise RuntimeError("index incomplete")
        jobs=[(task,mode) for task in TASKS for mode in ("baseline","pie")]
        random.Random(17).shuffle(jobs)
        rows=[]
        for (name,requirement,_),mode in jobs:
            if mode=="pie":
                evidence=smart_context(root,name,max_chars=8000,include_body=True,limit=2)
                if not any(x["symbol"]==name for x in evidence["evidence"]):
                    raise RuntimeError("missing target evidence")
                context=json.dumps(evidence,ensure_ascii=False)
            else:
                context=SOURCE
            data={"model":model,"max_tokens":1800,"stream":False,"messages":[
                {"role":"system","content":"Return only a JSON object with a single key named code, containing a complete Python function definition."},
                {"role":"user","content":f"Fix {name}: {requirement}\n\nSOURCE:\n{context}\n\nReturn a complete replacement function, keeping the same name."}]}
            request=urllib.request.Request(base+"/v1/chat/completions",
                 data=json.dumps(data).encode(),headers={"Content-Type":"application/json","Authorization":"Bearer "+key})
            row={"task":name,"mode":mode,"model":model}
            for attempt in range(3):
                start=time.perf_counter()
                try:
                    with urllib.request.urlopen(request,timeout=120) as response:
                        reply=json.load(response)
                    raw=(reply["choices"][0]["message"].get("content") or "").strip()
                    fence=chr(96)*3
                    if raw.startswith(fence):
                        raw=raw.split("\n",1)[-1].rsplit(fence,1)[0].strip()
                    try:
                        obj=json.loads(raw)
                        code=obj.get("code","") if isinstance(obj,dict) else ""
                    except ValueError:
                        code=raw if raw.lstrip().startswith("def ") or raw.lstrip().startswith("import ") else ""
                    row.update(ok=True,code=code,usage=reply.get("usage",{}),
                               finish_reason=reply["choices"][0].get("finish_reason"),
                               raw_length=len(raw),raw_excerpt=raw[:300] if not code else None,
                               parser_valid=bool(code),
                               seconds=round(time.perf_counter()-start,4))
                    break
                except urllib.error.HTTPError as err:
                    row.update(ok=False,http_status=err.code)
                    if err.code not in (502,503,504,529,530) or attempt==2:
                        break
                    time.sleep(2+2*attempt)
                except Exception as err:
                    row.update(ok=False,error=type(err).__name__)
                    break
            rows.append(row)
            destination.write_text(json.dumps({"results":rows},indent=2),encoding="utf8")
            print("GENERATED",name,mode,row.get("ok"),flush=True)

def verify_candidate(row,image):
    task=next((t for t in TASKS if t[0]==row["task"]),None)
    if not task or not row.get("ok") or not row.get("code"):
        return {"passed":False,"reason":"missing_candidate"}
    try:
        function=ast.parse(row["code"])
        matches=[n for n in function.body if isinstance(n,ast.FunctionDef) and n.name==task[0]]
        if len(matches)!=1:
            raise ValueError("target function not uniquely present")
        replacement=ast.get_source_segment(row["code"],matches[0])
        if not replacement:
            raise ValueError("cannot isolate function source")
        target=next(n for n in ast.parse(SOURCE).body if isinstance(n,ast.FunctionDef) and n.name==task[0])
        lines=SOURCE.splitlines(keepends=True)
        source="".join(lines[:target.lineno-1])+replacement.rstrip()+"\n"+"".join(lines[target.end_lineno:])
        compile(source,"service.py","exec")
    except (SyntaxError,ValueError,StopIteration):
        return {"passed":False,"reason":"invalid_patch"}
    with tempfile.TemporaryDirectory(prefix="pie-edit-") as folder:
        root=Path(folder)
        os.chmod(root,0o755)
        (root/"service.py").write_text(source,encoding="utf8")
        test=("import unittest\nfrom service import "+task[0]+" as f\n"
              "class TestBehavior(unittest.TestCase):\n    def test_examples(self):\n        "+task[2]+"\n")
        (root/"test_service.py").write_text(test,encoding="utf8")
        for f in root.iterdir():
            f.chmod(0o644)
        command=["docker","run","--rm","--network=none","--read-only","--cap-drop=ALL",
                 "--security-opt=no-new-privileges","--pids-limit=64","--memory=256m",
                 "--user=65534:65534","--tmpfs=/tmp:rw,nosuid,noexec,size=16m",
                 "-v",f"{root}:/work:ro","-w","/work",image,
                 "python","-B","-m","unittest","discover","-s","/work","-q"]
        start=time.perf_counter()
        try:
            proc=subprocess.run(command,text=True,capture_output=True,timeout=40)
            return {"passed":proc.returncode==0,"test_seconds":round(time.perf_counter()-start,3),
                    "test_exit_code":proc.returncode,"output":(proc.stdout+proc.stderr)[-1200:]}
        except subprocess.TimeoutExpired:
            return {"passed":False,"reason":"timeout"}
        except OSError:
            return {"passed":False,"reason":"docker_unavailable"}

def verify(source,destination,image):
    data=json.loads(source.read_text(encoding="utf8"))["results"]
    rows=[{**{k:v for k,v in row.items() if k!="code"},**verify_candidate(row,image)} for row in data]
    baseline={x["task"]:x for x in rows if x["mode"]=="baseline" and x.get("ok")}
    pairs=[(baseline[x["task"]],x) for x in rows if x["mode"]=="pie" and x.get("ok") and x["task"] in baseline]
    a=sum(x.get("usage",{}).get("prompt_tokens",0) for x,y in pairs)
    b=sum(y.get("usage",{}).get("prompt_tokens",0) for x,y in pairs)
    report={"scope":"Four curated synthetic code edits with executable isolated tests; not unseen production bugs",
            "pairs":len(pairs),"pair_token_saving_pct":round(100*(a-b)/a,2) if a else None,
            "pair_passed_baseline":sum(x["passed"] for x,y in pairs),
            "pair_passed_pie":sum(y["passed"] for x,y in pairs),
            "results":rows}
    destination.write_text(json.dumps(report,indent=2),encoding="utf8")
    print("CODE_EDIT_RESULT",json.dumps({k:v for k,v in report.items() if k!="results"}))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("generate","verify"),required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--input")
    p.add_argument("--model",default="gh/gpt-4o-mini")
    p.add_argument("--docker-image",default="python:3.12-slim")
    a=p.parse_args()
    if a.mode=="generate":
        generate(Path(a.output),a.model)
    else:
        verify(Path(a.input),Path(a.output),a.docker_image)
