"""Real-model autonomous PIE navigation lab via an OpenAI-compatible 9Router gateway.

The model chooses retrieval queries and receives actual PIE evidence through a
bounded tool loop. Source-derived oracles never enter model prompts. No code is
executed from model responses.
"""
from __future__ import annotations
import argparse
import ast
import json
import os
from pathlib import Path
import random
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from pie.indexing.indexer import index_project
from pie.retrieval.warm import WarmContextService

STOP = set("the and for with this that from which where what function method returns return into when each does how can are an all".split())

def terms(s):
    return set(re.findall(r"[a-z]{3,}", s.lower())) - STOP

def corpus_tasks(root, count, seed):
    choices = []
    for path in sorted((root/"rich").rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8-sig")
            if not 3500 <= len(source) <= 29000:
                continue
            tree = ast.parse(source)
        except (OSError, SyntaxError, UnicodeError):
            continue
        rel = path.relative_to(root).as_posix()
        nodes = [(n,n.name) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
        for cls in (n for n in tree.body if isinstance(n,ast.ClassDef)):
            nodes.extend((n,cls.name+"."+n.name) for n in cls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)))
        for n,name in nodes:
            summary = re.split(r"(?<=[.!?])\s+|\n",(ast.get_docstring(n) or "").strip(),1)[0]
            if 55 <= len(summary) <= 180 and len(terms(summary)) >= 6:
                choices.append({"query":"Find the implementation responsible for: "+summary,
                                "oracle":{"path":rel,"symbol":name}})
    random.Random(seed).shuffle(choices)
    selected=[]; seen=set()
    for x in choices:
        if x["oracle"]["path"] in seen:continue
        seen.add(x["oracle"]["path"]);selected.append(x)
        if len(selected)==count:break
    if len(selected)<count:raise RuntimeError(f"Not enough eligible Rich files: {len(selected)}")
    return selected

def chat(messages,model,base,key):
    data=json.dumps({"model":model,"messages":messages,"max_tokens":500,"stream":False}).encode()
    req=urllib.request.Request(base.rstrip("/")+"/v1/chat/completions",data=data,
        headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    start=time.perf_counter()
    with urllib.request.urlopen(req,timeout=120) as response:
        payload=json.load(response)
    raw=(payload["choices"][0]["message"].get("content") or "").strip()
    if raw.startswith("```"):
        raw=raw.split("\n",1)[-1].rsplit("```",1)[0].strip()
    try:answer=json.loads(raw)
    except ValueError:answer={"action":"invalid","raw_excerpt":raw[:150]}
    return answer,payload.get("usage",{}),time.perf_counter()-start

def perform(root,task,model,mode,base,key,service):
    system=("You navigate a real Python codebase. Return ONLY JSON, never markdown. "
            "For mode PIE, request indexed evidence first using "
            '{"action":"search","query":"your specific retrieval question"}. '
            'Once confident, return {"action":"answer","path":"relative/path.py","symbol":"Class.method or function"}. '
            "Never invent paths; answer only from available evidence. "
            "If uncertain, answer with empty path and symbol.")
    messages=[{"role":"system","content":system},
              {"role":"user","content":task["query"]+
               ("\nYou have a PIE search tool; ask for evidence." if mode=="pie" else
                "\nNo retrieval tool is available. Use the supplied candidate files.")}]
    if mode=="baseline":
        candidates=[]
        q=terms(task["query"])
        for p in sorted((root/"rich").rglob("*.py")):
            try:
                s=p.read_text(encoding="utf-8-sig")
            except (OSError,UnicodeError):continue
            if 3500<=len(s)<=29000:
                candidates.append((len(q & terms(s)),p,s))
        candidates.sort(key=lambda item:(-item[0],str(item[1])))
        body="\n\n".join(f"FILE {p.relative_to(root).as_posix()}\n{s}" for _,p,s in candidates[:2])
        messages.append({"role":"user","content":body[:55000]})
    used=0; calls=0; searches=0; search_ms=[]; answer={}
    for step in range(5):
        response,usage,elapsed=chat(messages,model,base,key)
        calls+=1;used+=usage.get("prompt_tokens",0)
        if response.get("action")=="answer":
            answer={"path":str(response.get("path","")).strip(),"symbol":str(response.get("symbol","")).strip()}
            break
        if mode=="pie" and response.get("action")=="search" and searches<3:
            question=response.get("query","")
            if not isinstance(question,str) or not question.strip():break
            start=time.perf_counter()
            result=service.query(question,max_chars=9000,limit=5,include_body=True)
            search_ms.append((time.perf_counter()-start)*1000)
            searches+=1
            messages.append({"role":"assistant","content":json.dumps(response)})
            messages.append({"role":"user","content":"PIE_SEARCH_RESULT "+json.dumps(result["result"],ensure_ascii=False)+
                             "\nYou may search again or answer with exact path and symbol."})
        else:
            break
    return {"mode":mode,"correct":answer==task["oracle"],"answer":answer,
            "calls":calls,"searches":searches,"prompt_tokens":used,
            "search_ms":search_ms}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--corpus",default="rich-corpus")
    p.add_argument("--models",default="gh/gpt-4o-mini")
    p.add_argument("--count",type=int,default=5)
    p.add_argument("--output",default="pie-agent-9router.json")
    args=p.parse_args()
    if not 1<=args.count<=20:p.error("count must be 1..20")
    base=os.getenv("PIE_API_BASE_URL","");key=os.getenv("PIE_API_KEY","")
    if not base.startswith("https://") or not key:
        raise RuntimeError("PIE_API_BASE_URL (HTTPS) and PIE_API_KEY required")
    root=Path(args.corpus).resolve()
    tasks=corpus_tasks(root,args.count,20261102)
    index=index_project(root)
    if index["index_state"]!="CURRENT":raise RuntimeError("Incomplete index")
    rows=[]
    with WarmContextService(root) as service:
        models=[m.strip() for m in args.models.split(";") if m.strip()]
        jobs=[(m,i,mode) for m in models for i in range(len(tasks)) for mode in ("pie","baseline")]
        random.Random(19).shuffle(jobs)
        for model,i,mode in jobs:
            try:
                result=perform(root,tasks[i],model,mode,base,key,service)
                result.update(model=model,task=i,ok=True)
            except (urllib.error.URLError,TimeoutError,ValueError,KeyError) as exc:
                result={"model":model,"task":i,"mode":mode,"ok":False,"error":type(exc).__name__}
            rows.append(result)
            Path(args.output).write_text(json.dumps({"results":rows},indent=2),encoding="utf8")
            print("AGENT",model,i,mode,result.get("correct"),result.get("error"),flush=True)
    report=[]
    for model in models:
        paired=[(next((r for r in rows if r["model"]==model and r["task"]==i and r["mode"]==mode),None)
                for mode in ("baseline","pie")) for i in range(len(tasks))]
        valid=[(a,b) for a,b in paired if a and b and a.get("ok") and b.get("ok")
               and a.get("prompt_tokens",0)>0]
        base_tokens=sum(a["prompt_tokens"] for a,b in valid)
        pie_tokens=sum(b["prompt_tokens"] for a,b in valid)
        report.append({"model":model,"completed_pairs":len(valid),"requested_pairs":len(tasks),
                       "baseline_correct":sum(a["correct"] for a,b in valid),
                       "pie_correct":sum(b["correct"] for a,b in valid),
                       "baseline_prompt_tokens":base_tokens,"pie_prompt_tokens":pie_tokens,
                       "token_saving_pct":round(100*(1-pie_tokens/base_tokens),2) if base_tokens else None})
    output={"scope":"Model-directed PIE tool loop on public Rich; docstring-derived oracles, no edits",
            "note":"Token usage accumulates all model calls. A/B includes different tools and prompts; errors are not counted as successful.",
            "models":report,"results":rows}
    Path(args.output).write_text(json.dumps(output,indent=2),encoding="utf8")
    print("AGENT_SUMMARY",json.dumps(report),flush=True)
    if any(x["completed_pairs"]!=x["requested_pairs"] for x in report):
        raise RuntimeError("Incomplete AI benchmark: inspect report and gateway availability")

if __name__=="__main__":
    main()
