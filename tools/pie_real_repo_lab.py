"""Real-repository PIE vs file-level discovery laboratory.

Corpus: separately checked out Textualize/rich (MIT), pinned by workflow ref.
No benchmark-specific answer maps in retrieval. Deterministic but diverse task
generation from AST docstrings, with source-derived oracle kept out of prompts.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import random
import re
import statistics
import time
import ipaddress
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from pie.indexing.indexer import index_project
from pie.graph.relationships import build_relationships
from pie.retrieval.context import build_context

STOP=set("the a an and of to with for in on is are from this that it which by as into at can be use using given when where how what returns return function method data value values object objects code class this will you not".split())

def terms(s):
    return {t for t in re.findall(r"[a-z]{3,}",s.lower()) if t not in STOP}

def source_inventory(root):
    rows=[]
    modules={}
    for file in sorted((root/"rich").rglob("*.py")):
        relative=file.relative_to(root).as_posix()
        source=file.read_text(encoding="utf-8-sig")
        if not 3500 <= len(source) <= 29000:continue
        try: tree=ast.parse(source)
        except SyntaxError:continue
        modules[relative]=source
        functions=[]
        for node in tree.body:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                functions.append((node,node.name))
            elif isinstance(node,ast.ClassDef):
                functions.extend((n,node.name+"."+n.name) for n in node.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)))
        for node,qualified in functions:
            desc=(ast.get_docstring(node) or "").strip()
            sentence=re.split(r"(?<=[.!?])\s+|\n",desc,1)[0].strip()
            snippet="\n".join(source.splitlines()[node.lineno-1:node.end_lineno])
            if (len(sentence)<45 or len(sentence)>190 or len(snippet)<70 or len(snippet)>2700
                or len(terms(sentence))<5 or sentence.lower().startswith("see ")):
                continue
            rows.append({"path":relative,"symbol":qualified,"line":node.lineno,
                         "snippet":snippet,"sentence":sentence})
    return modules,rows

def benchmark_tasks(rows,count,seed):
    # Stable selection BEFORE retrieval. One function per module to avoid clustering.
    rng=random.Random(seed)
    shuffled=rows[:]
    rng.shuffle(shuffled)
    selected=[];files=set()
    for row in shuffled:
        if row["path"] in files:continue
        files.add(row["path"])
        selected.append({"id":f"T{len(selected):02d}","question":
            ["Locate the Python function that performs this responsibility: ",
             "I need to change the implementation described here: ",
             "Where is the source code for this behavior: "][len(selected)%3]+row["sentence"],
            "oracle":{"path":row["path"],"symbol":row["symbol"]}})
        if len(selected)>=count:break
    if len(selected)<count:raise RuntimeError(f"Only {len(selected)} eligible modules; requested {count}")
    return selected

def search(question,modules,rows,budget):
    query=terms(question)
    scored_files=sorted(((len(query & terms(content)),path) for path,content in modules.items()),
                        key=lambda v:(-v[0],v[1]))
    # Traditional file-level search reads the two most overlapping complete files.
    candidate_paths=[p for score,p in scored_files if score>0][:2]
    # Source-level PIE retrieval ranks indexed function docstrings, not answers.
    ranked=sorted(((len(query & terms(r["sentence"]))*5+
                     len(query & terms(r["symbol"].replace("."," ").replace("_"," ")))*2,r)
                   for r in rows),key=lambda v:(-v[0],v[1]["path"],v[1]["line"]))
    chosen=[r for score,r in ranked if score>0][:4]
    pie="\n\n".join(f"{r['path']}:{r['line']} symbol={r['symbol']}\n{r['snippet']}" for r in chosen)
    baseline="\n\n".join(f"### {p}\n{modules[p]}" for p in candidate_paths)
    if len(baseline)>budget:
        # Do not silently truncate required files. Cap project file size at
        # admission time, and fail instead of suppressing evidence.
        raise RuntimeError(f"File context too big: {len(baseline)}")
    return baseline,pie,candidate_paths,chosen

def is_loopback_host(host):
    """True only when the hostname resolves to a loopback address."""
    if not isinstance(host,str) or not host:
        return False
    name=host.strip("[]")
    try:
        addresses=sorted({str(ipaddress.ip_address(a[4][0])) for a in socket.getaddrinfo(name,None)},
                         key=lambda v:(ipaddress.ip_address(v).version,))
    except (socket.gaierror,ValueError):
        return False
    if not addresses:
        return False
    return all(ipaddress.ip_address(a).is_loopback for a in addresses)

def validate_gateway_base_url(base):
    """Require HTTPS, or HTTP only against a loopback (localhost/127.0.0.1/::1) lab provider."""
    if not isinstance(base,str) or not base:
        return False
    parsed=urlparse(base)
    if parsed.scheme not in ("http","https") or not parsed.hostname:
        return False
    if parsed.scheme=="https":
        return True
    return is_loopback_host(parsed.hostname)

def require_gateway_secrets(base,key):
    """Fail closed without ever echoing the key."""
    if not key:raise RuntimeError("Missing PIE_API_KEY gateway secret")
    if not validate_gateway_base_url(base):
        raise RuntimeError("PIE_API_BASE_URL must be HTTPS, or HTTP against a loopback host (localhost/127.0.0.1/::1)")

BRACKET_PAIRS={"(":")","[":"]","{":"}"}

def normalize_navigation_answer(answer):
    """Accept a legitimate path:line citation without changing the symbol.

    The symbol may have exactly one outer balanced bracket pair wrapped
    around it (a known model failure mode). Strip that single pair and
    record whether normalization was applied; inner brackets are never
    touched, and the path is never bracket-stripped.
    """
    if not isinstance(answer,dict):return {}
    path=answer.get("path")
    symbol=answer.get("symbol")
    if not isinstance(path,str) or not isinstance(symbol,str):return {}
    path=re.sub(r"^#+\s*","",path.strip())
    path=re.sub(r":\d+(?:-\d+)?$","",path)
    symbol=symbol.strip()
    symbol_brackets_normalized=False
    if len(symbol)>=2:
        closer=BRACKET_PAIRS.get(symbol[0])
        if closer is not None and symbol.endswith(closer):
            inner=symbol[1:-1]
            # Strip only when the pair is truly outermost: all inner
            # delimiters must balance by type via an explicit stack, so
            # cross-wrapped cases like "[foo{bar]" or "[foo}bar]" are
            # rejected instead of silently normalized.
            stack=[];balanced=True
            for ch in inner:
                if ch in BRACKET_PAIRS:stack.append(ch)
                elif ch in BRACKET_PAIRS.values():
                    if not stack or BRACKET_PAIRS[stack[-1]]!=ch:
                        balanced=False;break
                    stack.pop()
            if balanced and not stack:
                symbol=inner.strip()
                symbol_brackets_normalized=True
    return {"path":path,"symbol":symbol,"symbol_brackets_normalized":symbol_brackets_normalized}

def normalize_usage(usage):
    """Classify provider-reported usage without inventing token counts.

    Status is "available" only when prompt_tokens and completion_tokens are
    non-negative integers (and total_tokens / cached tokens, when present, are
    too); otherwise every token field is None so missing data never becomes
    zero. Cache tokens may arrive as cached_input_tokens or nested under
    prompt_tokens_details.cached_tokens; their absence never changes status.
    """
    if not isinstance(usage,dict):usage={}
    fields={"prompt_tokens":None,"completion_tokens":None,"total_tokens":None,
            "cached_input_tokens":None,"uncached_input_tokens":None}
    def valid(v):return isinstance(v,int) and not isinstance(v,bool) and v>=0
    prompt=usage.get("prompt_tokens")
    completion=usage.get("completion_tokens")
    total=usage.get("total_tokens")
    details=usage.get("prompt_tokens_details")
    cached=usage.get("cached_input_tokens")
    if cached is None and isinstance(details,dict):
        cached=details.get("cached_tokens")
    if total is not None and not valid(total):
        return {"provider_usage_status":"unavailable",**fields}
    if cached is not None and not valid(cached):
        return {"provider_usage_status":"unavailable",**fields}
    if not valid(prompt) or not valid(completion):
        return {"provider_usage_status":"unavailable",**fields}
    if cached is not None and cached>prompt:
        return {"provider_usage_status":"unavailable",**fields}
    fields["prompt_tokens"]=prompt
    fields["completion_tokens"]=completion
    if total is not None:
        fields["total_tokens"]=total
    if cached is not None:
        fields["cached_input_tokens"]=cached
        fields["uncached_input_tokens"]=prompt-cached
    return {"provider_usage_status":"available",**fields}

def summarize_rows(rows,host=None,scheme=None,model=None,mode=None):
    """Aggregate one model/mode. Each token field is summed only when every
    successful call reported a valid value for that field; missing data never
    becomes zero, and fields are aggregated independently."""
    matching=list(rows)
    successes=[r for r in matching if r.get("ok")]
    have_usage=[r for r in successes if r.get("provider_usage_status")=="available"]
    usage_status="no_calls" if not matching else ("ok" if have_usage and len(have_usage)==len(successes) else "missing")
    def valid(v):return isinstance(v,int) and not isinstance(v,bool) and v>=0
    def total(key):
        if not successes:return None
        values=[r.get(key) for r in successes]
        if any(not valid(v) for v in values):return None
        return sum(values)
    return {"host":host,"scheme":scheme,"model":model,"mode":mode,"calls":len(matching),
            "successful":len(successes),"exact_correct":sum(1 for r in matching if r.get("correct")),
            "evidence_hit":sum(1 for r in matching if r.get("evidence_hit")),
            "provider_usage_status":usage_status,
            "prompt_tokens":total("prompt_tokens"),"completion_tokens":total("completion_tokens"),
            "total_tokens":total("total_tokens"),
            "cached_input_tokens":total("cached_input_tokens"),
            "uncached_input_tokens":total("uncached_input_tokens"),
            "median_latency_s":round(statistics.median(r["seconds"] for r in successes),4) if successes else None}

def infer(base,key,model,query,context,output_tokens):
    request_data={"model":model,"messages":[
        {"role":"system","content":"You are reading a real Python codebase. Return only valid JSON with keys path and symbol, both strings. The symbol must be the implementing function or Class.method. The symbol value must never contain brackets — do not wrap it in [], (), or {}. Cite exactly the supplied source paths. If evidence is insufficient, use empty strings."},
        {"role":"user","content":query+"\n\nCODE:\n"+context}
    ],"max_tokens":output_tokens,"stream":False}
    req=urllib.request.Request(base.rstrip("/")+"/v1/chat/completions",
        data=json.dumps(request_data).encode(),
        headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    begin=time.perf_counter()
    try:
        with urllib.request.urlopen(req,timeout=120) as response:payload=json.load(response)
        choice=payload["choices"][0]
        content=(choice["message"].get("content") or "").strip()
        fence=chr(96)*3
        if content.startswith(fence):content=content.split("\n",1)[-1].rsplit(fence,1)[0].strip()
        try:result=json.loads(content)
        except ValueError:result={}
        return {"ok":True,"answer":result,"seconds":round(time.perf_counter()-begin,4),
                "usage":payload.get("usage",{}),"finish_reason":choice.get("finish_reason"),
                "actual_model":payload.get("model")}
    except urllib.error.HTTPError as e:
        return {"ok":False,"error":"HTTP","http_status":e.code}
    except Exception as e:
        return {"ok":False,"error":type(e).__name__}

def run():
    p=argparse.ArgumentParser()
    p.add_argument("--corpus",default="rich-corpus")
    p.add_argument("--models",default="gh/gpt-4o-mini;nvidia/nemotron-3-ultra-550b-a55b")
    p.add_argument("--count",type=int,default=12)
    p.add_argument("--seed",type=int,default=20261102)
    p.add_argument("--max-baseline-chars",type=int,default=60000)
    p.add_argument("--output",default="rich-results")
    p.add_argument("--pie-production",action="store_true")
    p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    root=Path(a.corpus).resolve()
    output=Path(a.output);output.mkdir(parents=True,exist_ok=True)
    index_start=time.perf_counter()
    indexed=index_project(root)
    if indexed.get("index_state")!="CURRENT":
        raise RuntimeError("PIE source index is not CURRENT")
    relationships=build_relationships(root)
    index_seconds=round(time.perf_counter()-index_start,5)
    modules,rows=source_inventory(root)
    tasks=benchmark_tasks(rows,a.count,a.seed)
    evidence={};audit=[]
    for task in tasks:
        start=time.perf_counter()
        baseline,pie,files,selected=search(task["question"],modules,rows,a.max_baseline_chars)
        if a.pie_production:
            resolved=build_context(root,task["question"],max_chars=12000,limit=4,strategy="smart")
            pie=json.dumps(resolved,ensure_ascii=False)
            selected=[{"path":e["path"],"symbol":e["symbol"]} for e in resolved["evidence"]]
        retrieval=time.perf_counter()-start
        present_baseline=task["oracle"]["path"] in files
        present_pie=any(x["path"]==task["oracle"]["path"] and x["symbol"]==task["oracle"]["symbol"] for x in selected)
        audit.append({"id":task["id"],"oracle":task["oracle"],"baseline_hit":present_baseline,
                      "pie_hit":present_pie,"baseline_chars":len(baseline),"pie_chars":len(pie),
                      "retrieval_seconds":round(retrieval,6)})
        evidence[task["id"]]={"baseline":baseline,"pie":pie}
    (output/"audit.json").write_text(json.dumps({"tasks":tasks,"audit":audit},indent=2),encoding="utf8")
    print("REAL_CORPUS_AUDIT",json.dumps({"modules":len(modules),"eligible_functions":len(rows),"tasks":len(tasks),
          "baseline_hits":sum(x["baseline_hit"] for x in audit),
          "pie_hits":sum(x["pie_hit"] for x in audit),
          "median_baseline_chars":statistics.median(x["baseline_chars"] for x in audit),
          "median_pie_chars":statistics.median(x["pie_chars"] for x in audit),"index_seconds":index_seconds,"relationships_stored":relationships.get("stored")}),flush=True)
    if a.dry_run:return
    base=os.getenv("PIE_API_BASE_URL","")
    key=os.getenv("PIE_API_KEY","")
    require_gateway_secrets(base,key)
    results=[];models=a.models.split(";")
    for model in models:
        jobs=[(task,mode) for task in tasks for mode in ("baseline","pie")]
        random.Random(a.seed).shuffle(jobs)
        for task,mode in jobs:
            reply=infer(base,key,model,task["question"],evidence[task["id"]][mode],
                         900 if "nemotron" in model.lower() else 160)
            normalized=normalize_navigation_answer(reply.get("answer"))
            correct=bool(normalized) and normalized.get("path")==task["oracle"]["path"] and normalized.get("symbol")==task["oracle"]["symbol"]
            usage=reply.get("usage") if isinstance(reply.get("usage"),dict) else {}
            provider_fields=normalize_usage(usage)
            row={"model":model,"task":task["id"],"mode":mode,"correct":correct,
                 "normalized_answer":normalized,"evidence_hit":next(x[mode+"_hit"] for x in audit if x["id"]==task["id"]),**reply,**provider_fields}
            results.append(row)
            (output/"results.json").write_text(json.dumps({"results":results},indent=2),encoding="utf8")
            print("RUN",model,task["id"],mode,"correct="+str(correct),"ok="+str(reply["ok"]),
                  "seconds="+str(reply.get("seconds")),flush=True)
            time.sleep(.15)
    summary=[]
    for model in models:
        for mode in ("baseline","pie"):
            matching=[r for r in results if r["model"]==model and r["mode"]==mode]
            summary.append(summarize_rows(matching,host=urlparse(base).hostname,
                                          scheme=urlparse(base).scheme,model=model,mode=mode))
    (output/"summary.json").write_text(json.dumps({"results":summary,
         "index_seconds":index_seconds,"qualification":"Real open-source Rich codebase, generated docstring queries. File-level vs function-level retrieval; no full repository baseline and no edit tasks."},indent=2),encoding="utf8")
    print("REAL_CORPUS_SUMMARY",json.dumps(summary),flush=True)

if __name__=="__main__":run()
