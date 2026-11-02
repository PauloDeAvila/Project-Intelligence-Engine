#!/usr/bin/env python3
"""60-task GPT-only context efficiency lab across three real Python repositories.

Controlled comparison of file-level lexical retrieval versus AST symbol-level
retrieval. An independent source-derived oracle is never included in prompts.
This is *not* a full agent implementing code, and is not the PIE production
context API: report that distinction when interpreting results.
"""
from __future__ import annotations
import argparse
import ast
import collections
import hashlib
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pie.indexing.indexer import index_project
from pie.graph.relationships import build_relationships

PROJECTS = (("rich", "rich"), ("click", "src/click"), ("httpx", "httpx"))
STOP = set(("the a an to in on with for from when where which what who how this that "
            "your their his her its class function method code source implementation "
            "find locate change modify responsible handling handles perform returns "
            "return use uses using implements help need want does and or of as by at "
            "are was be can via an argument value data object given following").split())
def words(text):
    return set(x for x in re.findall(r"[a-z]{3,}", text.lower()) if x not in STOP)

def inventory(project, root, relative_source):
    items=[];files={}
    source=root/relative_source
    if not source.is_dir():raise RuntimeError("Corpus source folder missing: "+str(source))
    for path in sorted(source.rglob("*.py")):
        if path.name.startswith("test_"):continue
        content=path.read_text(encoding="utf-8-sig")
        if not 1000 <= len(content) <= 35000:continue
        try:tree=ast.parse(content)
        except SyntaxError:continue
        rel=path.relative_to(root).as_posix()
        files[rel]=content
        defs=[]
        for node in tree.body:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                defs.append((node,node.name))
            if isinstance(node,ast.ClassDef):
                defs.extend((m,node.name+"."+m.name) for m in node.body
                            if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)))
        for node,symbol in defs:
            doc=ast.get_docstring(node) or ""
            first=re.split(r"\n|(?<=[.!?])\s+",doc.strip(),maxsplit=1)[0].strip()
            code="\n".join(content.splitlines()[node.lineno-1:node.end_lineno])
            if not 35<=len(first)<=210 or len(words(first))<4:continue
            if not 45 <= len(code) <= 4200:continue
            if first.lower().startswith(("see ", "the ", "return ")):continue
            items.append({"project":project,"path":rel,"symbol":symbol,"line":node.lineno,
                          "doc":first,"code":code})
    return files,items

def make_tasks(project, items, n, seed):
    r=random.Random(seed)
    shuffled=list(items)
    r.shuffle(shuffled)
    used_symbols=set(); file_load=collections.Counter();tasks=[]
    for row in shuffled:
        identity=(row["path"],row["symbol"])
        if identity in used_symbols or file_load[row["path"]]>=3:continue
        used_symbols.add(identity);file_load[row["path"]]+=1
        intro=("Find the implementation of this behavior: ",
               "Which function would you change to modify this behavior: ",
               "Where is the function responsible for this operation: ")[len(tasks)%3]
        tasks.append({"id":f"{project}-{len(tasks):02d}","project":project,
                      "question":intro+row["doc"],
                      "oracle":{"path":row["path"],"symbol":row["symbol"]}})
        if len(tasks)>=n:break
    if len(tasks)!=n:raise RuntimeError(f"{project}: only {len(tasks)} eligible tasks of {n}")
    return tasks

def retrieve(task,files,items,policy="top2"):
    q=words(task["question"])
    # Baseline emulates a conventional local search reading complete files.
    rank_files=sorted(((len(q & words(source)),path) for path,source in files.items()),
                      key=lambda x:(-x[0],x[1]))
    base_files=[p for score,p in rank_files if score>0][:2]
    if sum(len(files[p]) for p in base_files)>38000:base_files=base_files[:1]
    baseline="\n\n".join("### "+p+"\n"+files[p] for p in base_files)
    # PIE-inspired structural retrieval: AST documents + symbol identifiers.
    scores=[]
    for row in items:
        score=6*len(q & words(row["doc"]))+2*len(q & words(row["symbol"].replace("_"," ").replace("."," ")))
        if score>0:scores.append((score,row))
    scores.sort(key=lambda pair:(-pair[0],pair[1]["path"],pair[1]["line"]))
    limit=2 if policy=="top2" else 3
    chosen=[row for _,row in scores[:limit]]
    pie="\n\n".join(f"{row['path']}:{row['line']} | {row['symbol']}\nResponsibility: {row['doc']}\nSignature: {next((line.strip() for line in row['code'].splitlines() if line.lstrip().startswith(('def ','async def '))), '')}" for row in chosen)
    hit=any(row["path"]==task["oracle"]["path"] and row["symbol"]==task["oracle"]["symbol"]
            for row in chosen)
    base_hit=task["oracle"]["path"] in base_files
    return {"baseline":baseline,"pie":pie,"pie_hit":hit,"baseline_hit":base_hit,
            "selected":[{"path":x["path"],"symbol":x["symbol"]} for x in chosen]}

def normalized_answer(answer):
    if not isinstance(answer,dict):return {}
    path=answer.get("path")
    symbol=answer.get("symbol")
    if not isinstance(path,str) or not isinstance(symbol,str):return {}
    path=re.sub(r":\d+(?:-\d+)?$","",path.strip())
    return {"path":path,"symbol":symbol.strip()}

def call(base,key,model,question,context):
    payload={"model":model,"messages":[
        {"role":"system","content":"You are a code navigation assistant. Use SOURCE only, never invent files. Return only a JSON object with exact keys path and symbol, both strings. For nested functions use Class.method. If the requested implementation is not supported by the provided source, return empty strings. A file path may include :line."},
        {"role":"user","content":question+"\n\nSOURCE:\n"+context}
    ],"max_tokens":160,"stream":False}
    req=urllib.request.Request(base.rstrip("/")+"/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    start=time.perf_counter()
    try:
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req,timeout=95) as response:obj=json.load(response)
                break
            except urllib.error.HTTPError as err:
                if err.code not in (502,503,504,529,530) or attempt==3:raise
                time.sleep((1.5,3,6)[attempt])
        choice=obj["choices"][0]
        body=(choice.get("message",{}).get("content") or "").strip()
        fence=chr(96)*3
        if body.startswith(fence):body=body.split("\n",1)[-1].rsplit(fence,1)[0].strip()
        try:answer=json.loads(body)
        except ValueError:answer={}
        return {"ok":True,"answer":normalized_answer(answer),"usage":obj.get("usage",{}),
                "finish_reason":choice.get("finish_reason"),
                "seconds":round(time.perf_counter()-start,4)}
    except urllib.error.HTTPError as e:
        return {"ok":False,"error":"HTTP","status":e.code,
                "seconds":round(time.perf_counter()-start,4)}
    except Exception as e:
        return {"ok":False,"error":type(e).__name__,
                "seconds":round(time.perf_counter()-start,4)}

def summarise(results, audit):
    out=[]
    for mode in ("baseline","pie"):
        subset=[r for r in results if r["mode"]==mode]
        success=[r for r in subset if r["ok"]]
        tokens=[r.get("usage",{}).get("prompt_tokens") for r in success]
        out.append({"mode":mode,"calls":len(subset),"successful":len(success),
                    "correct":sum(r.get("correct",False) for r in subset),
                    "prompt_tokens":sum(x for x in tokens if isinstance(x,int)),
                    "median_latency_s":round(statistics.median(r["seconds"] for r in success),4) if success else None})
    lookup={(r["task"],r["mode"]):r for r in results}
    pairs=[]
    for row in audit:
        a=lookup.get((row["task"],"baseline"))
        b=lookup.get((row["task"],"pie"))
        if not a or not b or not a["ok"] or not b["ok"]:continue
        u=a.get("usage",{}).get("prompt_tokens")
        v=b.get("usage",{}).get("prompt_tokens")
        if not isinstance(u,int) or not isinstance(v,int):continue
        pairs.append({"task":row["task"],"tokens_baseline":u,"tokens_pie":v,
                      "seconds_baseline":a["seconds"],"seconds_pie":b["seconds"],
                      "baseline_correct":a["correct"],"pie_correct":b["correct"]})
    a_tokens=sum(x["tokens_baseline"] for x in pairs)
    b_tokens=sum(x["tokens_pie"] for x in pairs)
    paired={"pairs":len(pairs),"baseline_tokens":a_tokens,"pie_tokens":b_tokens,
            "saving_pct":round(100*(1-b_tokens/a_tokens),3) if a_tokens else None,
            "both_correct":sum(x["baseline_correct"] and x["pie_correct"] for x in pairs),
            "baseline_correct":sum(x["baseline_correct"] for x in pairs),
            "pie_correct":sum(x["pie_correct"] for x in pairs),
            "pie_faster_pairs":sum(x["seconds_pie"]<x["seconds_baseline"] for x in pairs)}
    return out,paired,pairs

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",default="benchmark-corpora")
    parser.add_argument("--tasks-per-repo",type=int,default=20)
    parser.add_argument("--policy",choices=("top2","top3"),default="top2")
    parser.add_argument("--model",default="gh/gpt-4o-mini")
    parser.add_argument("--seed",type=int,default=681997)
    parser.add_argument("--out",default="gpt-multirepo-results")
    parser.add_argument("--dry-run",action="store_true")
    a=parser.parse_args()
    if not 1<=a.tasks_per_repo<=30:parser.error("tasks-per-repo must be 1..30")
    folder=Path(a.root)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    tasks=[]; contexts={}; audit=[]; corpus=[]
    for i,(project,subpath) in enumerate(PROJECTS):
        source=folder/project
        t0=time.perf_counter()
        ix=index_project(source)
        if ix.get("index_state")!="CURRENT":raise RuntimeError("PIE index stale: "+project)
        relations=build_relationships(source)
        indexing=round(time.perf_counter()-t0,5)
        files,items=inventory(project,source,subpath)
        repo_tasks=make_tasks(project,items,a.tasks_per_repo,a.seed+10*i)
        corpus.append({"repo":project,"files":len(files),"eligible_symbols":len(items),
                       "index_and_graph_seconds":indexing,"relationships":relations.get("stored")})
        for task in repo_tasks:
            started=time.perf_counter()
            result=retrieve(task,files,items,a.policy)
            elapsed=round(time.perf_counter()-started,6)
            contexts[task["id"]]=result
            audit.append({"task":task["id"],"project":project,
                          "pie_hit":result["pie_hit"],"baseline_hit":result["baseline_hit"],
                          "pie_chars":len(result["pie"]),"baseline_chars":len(result["baseline"]),
                          "local_retrieval_seconds":elapsed,"selected":result["selected"]})
            tasks.append(task)
    (out/"audit.json").write_text(json.dumps({"corpora":corpus,"tasks":tasks,"audit":audit,
       "policy":a.policy},ensure_ascii=False,indent=2),encoding="utf-8")
    print("AUDIT",json.dumps({"corpora":corpus,"tasks":len(tasks),"pie_hits":sum(t["pie_hit"] for t in audit),
           "baseline_hits":sum(t["baseline_hit"] for t in audit),
           "median_baseline_chars":statistics.median(t["baseline_chars"] for t in audit),
           "median_pie_chars":statistics.median(t["pie_chars"] for t in audit)}),flush=True)
    if a.dry_run:return
    base=os.environ.get("PIE_API_BASE_URL","")
    key=os.environ.get("PIE_API_KEY","")
    if not base.startswith("https://") or not key:raise RuntimeError("Missing gateway secrets")
    jobs=[(task,mode) for task in tasks for mode in ("baseline","pie")]
    random.Random(a.seed+481).shuffle(jobs)
    results=[]
    for i,(task,mode) in enumerate(jobs,1):
        r=call(base,key,a.model,task["question"],contexts[task["id"]][mode])
        item={"task":task["id"],"project":task["project"],"mode":mode,
              "correct":r.get("answer")==task["oracle"],**r}
        results.append(item)
        (out/"results.json").write_text(json.dumps({"results":results},ensure_ascii=False,indent=2),encoding="utf-8")
        print("CALL",f"{i}/{len(jobs)}",task["id"],mode,"ok",r["ok"],"correct",item["correct"],
              "time",r["seconds"],flush=True)
        time.sleep(.20)
    overall,paired,pairs=summarise(results,audit)
    byrepo={}
    for repo, _ in PROJECTS:
        rows=[r for r in results if r["project"]==repo]
        r_a=[t for t in audit if t["project"]==repo]
        byrepo[repo]={"summary":summarise(rows,r_a)[0],"paired":summarise(rows,r_a)[1]}
    (out/"summary.json").write_text(json.dumps({"overall":overall,"paired":paired,
        "by_repo":byrepo,"pair_rows":pairs,"corpora":corpus,
        "qualification":"New seeded holdout tasks on real Python source. Baseline reads top-two source files (top-one when input budget overflows); PIE supplies AST signature and docstring navigation cards. Location lookup only, not autonomous editing. Source oracle not supplied.",
        "indexing_excluded_from_inference_latency":True},ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({"overall":overall,"paired":paired,"byrepo":byrepo}),flush=True)
if __name__=="__main__":main()
