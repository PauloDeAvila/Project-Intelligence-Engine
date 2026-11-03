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
            if not 1500 <= len(source) <= 80000:
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
    selected=[]; seen=set(); per_file={}
    for x in choices:
        key=(x["oracle"]["path"],x["oracle"]["symbol"])
        if key in seen or per_file.get(key[0],0)>=2:continue
        seen.add(key);per_file[key[0]]=per_file.get(key[0],0)+1;selected.append(x)
        if len(selected)==count:break
    if len(selected)<count:raise RuntimeError(f"Not enough eligible Rich files: {len(selected)}")
    return selected

def chat(messages,model,base,key):
    max_tokens = int(os.getenv("PIE_MODEL_MAX_TOKENS", "2048"))
    if not 128 <= max_tokens <= 8192:
        raise ValueError("PIE_MODEL_MAX_TOKENS must be between 128 and 8192")
    data=json.dumps({"model":model,"messages":messages,"max_tokens":max_tokens,"stream":False}).encode()
    req=urllib.request.Request(base.rstrip("/")+"/v1/chat/completions",data=data,
        headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    start=time.perf_counter()
    payload=None
    status=None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=45) as response:
                status=getattr(response,"status",None)
                payload=json.load(response)
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 429, 500, 502, 503, 504) or attempt == 2:
                raise
            retry_after=exc.headers.get("Retry-After")
            try:
                delay=min(30.0,max(0.0,float(retry_after))) if retry_after else 3.0*(2**attempt)
            except ValueError:
                delay=3.0*(2**attempt)
            print("RETRY",model,"http",exc.code,"attempt",attempt+1,"delay_s",delay,flush=True)
            time.sleep(delay)
        except (TimeoutError, urllib.error.URLError) as exc:
            if attempt == 2:
                raise
            delay=3.0*(2**attempt)
            print("RETRY",model,type(exc).__name__,"attempt",attempt+1,"delay_s",delay,flush=True)
            time.sleep(delay)
    choice=payload["choices"][0]
    message=choice.get("message") or {}
    content=message.get("content")
    if isinstance(content,str):
        raw=content.strip()
    elif isinstance(content,list):
        raw="".join(part.get("text","") for part in content if isinstance(part,dict)).strip()
    else:
        raw=""
    reasoning=message.get("reasoning_content") or message.get("reasoning") or ""
    diagnostics={
        "http_status":status,
        "finish_reason":choice.get("finish_reason"),
        "content_chars":len(raw),
        "reasoning_chars":len(reasoning) if isinstance(reasoning,str) else None,
        "message_fields":sorted(message.keys()),
    }
    if raw.startswith("```"):
        raw=raw.split("\n",1)[-1].rsplit("```",1)[0].strip()
    try:
        answer=json.loads(raw)
        if not isinstance(answer,dict):
            answer={"action":"invalid","raw_excerpt":raw[:150]}
    except (ValueError,TypeError):
        answer={"action":"invalid","raw_excerpt":raw[:150]}
    diagnostics["parsed_action"]=answer.get("action")
    return answer,payload.get("usage") or {},time.perf_counter()-start,diagnostics

def gateway_failure(exc):
    """Safe transport diagnosis without printing endpoint URLs or API keys."""
    if isinstance(exc, urllib.error.HTTPError):
        return {"category": "http_error", "http_status": exc.code,
                "reason_type": "HTTPError"}
    reason = getattr(exc, "reason", exc)
    name = type(reason).__name__
    message = str(reason).lower()
    if "gaierror" in name or "name resolution" in message or "name or service not known" in message:
        category = "dns_resolution_failed"
    elif isinstance(reason, (TimeoutError,)) or "timed out" in message:
        category = "timeout"
    elif "connectionrefused" in name.lower() or "connection refused" in message:
        category = "connection_refused"
    elif "ssl" in name.lower() or "certificate" in message:
        category = "tls_error"
    elif "network is unreachable" in message:
        category = "network_unreachable"
    else:
        category = "transport_error"
    return {"category": category, "http_status": None, "reason_type": name}


def probe_gateway(base, key, model):
    """One real inference request before the expensive paired benchmark."""
    try:
        _, _, _, diagnostics = chat(
            [{"role": "user", "content": 'Return {"action":"answer","path":"","symbol":""} as JSON.'}],
            model, base, key)
        return {"ok": True, "model": model, "http_status": diagnostics["http_status"]}
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
        return {"ok": False, "model": model, **gateway_failure(exc)}


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
            if 1500<=len(s)<=80000:
                candidates.append((len(q & terms(s)),p,s))
        candidates.sort(key=lambda item:(-item[0],str(item[1])))
        body="\n\n".join(f"FILE {p.relative_to(root).as_posix()}\n{s}" for _,p,s in candidates[:2])
        # Bound baseline context to avoid gateway HTTP 400 on oversized candidate bodies.
        # Keep this independent of PIE retrieval; failed attempts remain failures.
        messages.append({"role":"user","content":body[:16000]})
    used=0; output_used=0; calls=0; searches=0; search_ms=[]; model_ms=[]; answer={}; response_diagnostics=[]
    prompt_usage_calls=0; completion_usage_calls=0
    for step in range(5):
        response,usage,elapsed,diagnostics=chat(messages,model,base,key)
        calls+=1
        response_diagnostics.append(diagnostics)
        if isinstance(usage.get("prompt_tokens"),int):
            used+=usage["prompt_tokens"]; prompt_usage_calls+=1
        if isinstance(usage.get("completion_tokens"),int):
            output_used+=usage["completion_tokens"]; completion_usage_calls+=1
        model_ms.append(round(elapsed*1000,3))
        if response.get("action")=="answer":
            answer={"path":str(response.get("path","")).strip(),"symbol":str(response.get("symbol","")).strip()}
            break
        if mode=="pie" and response.get("action")=="search" and searches<3:
            question=response.get("query","")
            if not isinstance(question,str) or not question.strip():break
            start=time.perf_counter()
            result=service.task_pack(question,max_chars=12000,limit=5)
            predicted=service.predictive_prefetch(question,limit=4)
            result={"responsibility_pack":result,"predictive_prefetch":predicted}
            search_ms.append((time.perf_counter()-start)*1000)
            searches+=1
            messages.append({"role":"assistant","content":json.dumps(response)})
            messages.append({"role":"user","content":"PIE_SEARCH_RESULT "+json.dumps(result,ensure_ascii=False)+
                             "\nYou may search again or answer with exact path and symbol."})
        else:
            break
    return {"mode":mode,"correct":answer==task["oracle"],"answer":answer,
            "answer_valid":bool(answer.get("path") and answer.get("symbol")),
            "response_diagnostics":response_diagnostics,
            "oracle":task["oracle"],"query":task["query"],
            "calls":calls,"searches":searches,
            "prompt_usage_calls":prompt_usage_calls,"completion_usage_calls":completion_usage_calls,
            "prompt_tokens":used if prompt_usage_calls==calls else None,
            "search_ms":search_ms,"model_ms":model_ms,
            "completion_tokens":output_used if completion_usage_calls==calls else None}

def summarize_model_results(rows, models, expected_questions):
    """Eagerly match each task once. Never reuse a late-bound generator's last task."""
    report = []
    for model in models:
        indexed = {(r["task"], r["mode"]): r for r in rows if r.get("model") == model}
        pairs = [
            (indexed.get((task, "baseline")), indexed.get((task, "pie")))
            for task in range(expected_questions)
        ]
        valid = [(a, b) for a, b in pairs
                 if a is not None and b is not None and a.get("ok") is True and b.get("ok") is True]
        token_pairs = [(a, b) for a, b in valid
                       if type(a.get("prompt_tokens")) is int and type(b.get("prompt_tokens")) is int]
        base_tokens = sum(a["prompt_tokens"] for a, b in token_pairs)
        pie_tokens = sum(b["prompt_tokens"] for a, b in token_pairs)
        report.append({
            "model": model, "completed_pairs": len(valid),
            "requested_pairs": expected_questions,
            "baseline_correct": sum(a.get("correct") is True for a, b in valid),
            "pie_correct": sum(b.get("correct") is True for a, b in valid),
            "baseline_prompt_tokens": base_tokens if token_pairs else None,
            "pie_prompt_tokens": pie_tokens if token_pairs else None,
            "token_covered_pairs": len(token_pairs),
            "token_saving_pct": round(100 * (1 - pie_tokens / base_tokens), 2)
                if base_tokens > 0 and token_pairs else None,
        })
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--corpus",default="rich-corpus")
    p.add_argument("--models",default="qd/qfmodel")
    p.add_argument("--count",type=int,default=30)
    p.add_argument("--cooldown-seconds",type=float,default=15.0)
    p.add_argument("--output",default="pie-agent-9router.json")
    args=p.parse_args()
    if not 1<=args.count<=60:p.error("count must be 1..60")
    if not 0<=args.cooldown_seconds<=120:p.error("cooldown must be 0..120 seconds")
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
        preflight=[probe_gateway(base,key,m) for m in models]
        print("GATEWAY_PREFLIGHT",json.dumps(preflight),flush=True)
        if not all(item["ok"] for item in preflight):
            Path(args.output).write_text(json.dumps({
                "scope":"Preflight only; no benchmark attempts executed",
                "gateway_preflight":preflight,"results":[]},indent=2),encoding="utf8")
            raise RuntimeError("Gateway preflight failed: inspect transport category and GitHub Actions connectivity")
        jobs=[(m,i,mode) for m in models for i in range(len(tasks)) for mode in ("pie","baseline")]
        random.Random(19).shuffle(jobs)
        for position,(model,i,mode) in enumerate(jobs):
            if position:
                print("COOLDOWN",args.cooldown_seconds,"seconds",flush=True)
                time.sleep(args.cooldown_seconds)
            started=time.perf_counter()
            try:
                result=perform(root,tasks[i],model,mode,base,key,service)
                result.update(model=model,task=i,ok=True)
            except (urllib.error.URLError,TimeoutError,ValueError,KeyError) as exc:
                result={"model":model,"task":i,"mode":mode,"ok":False,"correct":None,
                        "oracle":tasks[i]["oracle"],"query":tasks[i]["query"],
                        "error":type(exc).__name__,"error_detail":str(exc)[:300],
                        "http_status":exc.code if isinstance(exc,urllib.error.HTTPError) else None}
            result["attempt_wall_ms"]=round((time.perf_counter()-started)*1000,3)
            rows.append(result)
            Path(args.output).write_text(json.dumps({"results":rows},indent=2),encoding="utf8")
            print("AGENT",model,i,mode,result.get("correct"),result.get("error"),
                  "response_diagnostics",json.dumps(result.get("response_diagnostics",[])),flush=True)
    report=summarize_model_results(rows,models,len(tasks))
    output={"gateway_preflight":preflight,
            "scope":"Model-directed PIE tool loop on public Rich; docstring-derived oracles, no edits",
            "note":"Token usage accumulates all model calls. A/B includes different tools and prompts; errors are not counted as successful.",
            "models":report,"results":rows}
    Path(args.output).write_text(json.dumps(output,indent=2),encoding="utf8")
    print("AGENT_SUMMARY",json.dumps(report),flush=True)
    if any(x["completed_pairs"]!=x["requested_pairs"] for x in report):
        raise RuntimeError("Incomplete AI benchmark: inspect report and gateway availability")

if __name__=="__main__":
    main()
