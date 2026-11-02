"""Multi-model code navigation benchmark: distinct prompts, independent AST oracle."""
import argparse, ast, json, os, random, re, statistics, tempfile, time, urllib.request, urllib.error
from pathlib import Path
from cloud_pie_benchmark import LAB, synthetic_modules
from pie.indexing.indexer import index_project
from pie.graph.relationships import build_relationships

FEATURES=[
("billing","prorate_invoice","partial subscription invoice when changing billing plan"),
("identity","expire_session","invalidate an authenticated session after its expiration timestamp"),
("storage","dedupe_chunks","eliminate repeated uploaded file chunks by content digest"),
("shipping","route_parcel","choose a shipping carrier for parcel weight and zone"),
("geometry","clip_polygon","clip polygon vertices inside a rectangular canvas"),
("analytics","rolling_average","compute moving averages over telemetry readings"),
("security","scrub_secrets","redact credentials before writing log output"),
("catalog","apply_discount","apply percentage discount to catalog item price"),
("notifications","throttle_email","restrict email notifications within a rate window"),
("media","normalize_gain","normalize audio samples by peak amplitude"),
("scheduling","skip_holidays","remove public holidays from workday candidates"),
("inventory","reorder_stock","calculate replenishment quantity from minimum stock threshold")]
STOP=set("the a an to from what which where is does function code source implementation for with how find locate of in and please that this we want need task module file path who calls".split())
def terms(s):return set(w for w in re.findall(r"[a-z]{3,}",s.lower()) if w not in STOP)
def fixture(root,scale):
    for p,s in list(LAB.items())+list(synthetic_modules(scale)):
        path=root/p;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(s,encoding="utf8")
    for domain,name,doc in FEATURES:
        a=root/("application/"+domain+".py")
        a.parent.mkdir(parents=True,exist_ok=True)
        a.write_text("def "+name+"(value, adjustment=1):\n    "+repr(doc)+"\n    if value is None: raise ValueError('missing')\n    return value * adjustment\n",encoding="utf8")
        b=root/("workflows/"+domain+"_flow.py")
        b.parent.mkdir(parents=True,exist_ok=True)
        b.write_text("from application."+domain+" import "+name+"\ndef run_"+name+"(value):\n    "+repr("Workflow uses "+name+" to "+doc)+"\n    return "+name+"(value)\n",encoding="utf8")
    for p in ("application/__init__.py","workflows/__init__.py"):(root/p).write_text("")
def tasks():
    out=[]
    for i,(domain,name,doc) in enumerate(FEATURES):
        caller=i%3==2
        q=("Which workflow function calls "+name+"? Provide its path and symbol." if caller else
           ["Where is the code responsible for "+doc+"?","I need to modify the feature that can "+doc+". Find its definition.","Find the exact function and file that handle "+doc+"."][i%3])
        out.append({"id":i,"kind":"caller" if caller else "location","question":q,
                    "expected":{"path":("workflows/"+domain+"_flow.py" if caller else "application/"+domain+".py"),
                                "symbol":("run_"+name if caller else name)}})
    return out
def entries(root):
    out=[]
    for path in sorted(root.rglob("*.py")):
        if ".pie" in path.parts:continue
        source=path.read_text(encoding="utf8")
        try:tree=ast.parse(source)
        except SyntaxError:continue
        for n in tree.body:
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                out.append({"path":path.relative_to(root).as_posix(),"symbol":n.name,
                            "source":"\n".join(source.splitlines()[n.lineno-1:n.end_lineno]),
                            "doc":ast.get_docstring(n) or "","lineno":n.lineno,
                            "calls":{c.func.id for c in ast.walk(n) if isinstance(c,ast.Call) and isinstance(c.func,ast.Name)}})
    return out
def retrieve(task,items):
    q=terms(task["question"])
    ranks=[]
    for e in items:
        score=5*len(q & terms(e["symbol"].replace("_"," ")))+3*len(q & terms(e["doc"]))+len(q & terms(e["path"].replace("/"," ").replace("_"," ")))
        if task["kind"]=="caller":score+=10*sum(name in task["question"] for name in e["calls"])
        if score:ranks.append((score,e))
    ranks.sort(key=lambda pair:(-pair[0],pair[1]["path"],pair[1]["symbol"]))
    selected=[e for _,e in ranks[:4]]
    context="\n\n".join(e["path"]+":"+str(e["lineno"])+" "+e["symbol"]+"\n"+e["source"] for e in selected)
    hit=any({"path":e["path"],"symbol":e["symbol"]}==task["expected"] for e in selected)
    return context,hit
def request(base,key,model,task,context):
    data={"model":model,"messages":[{"role":"system","content":"Navigate code using supplied evidence only. Return a single JSON object with exactly path and symbol fields as strings. If insufficient evidence, use empty strings."},{"role":"user","content":task["question"]+"\n\nSOURCE:\n"+context}],"max_tokens":768 if "nemotron" in model.lower() else 120,"stream":False}
    req=urllib.request.Request(base.rstrip("/")+"/v1/chat/completions",data=json.dumps(data).encode(),headers={"Content-Type":"application/json","Authorization":"Bearer "+key})
    t=time.perf_counter()
    try:
        with urllib.request.urlopen(req,timeout=110) as response:payload=json.load(response)
        content=(payload["choices"][0]["message"].get("content") or "").strip()
        if content.startswith(chr(96)*3):content=content.split("\n",1)[-1].rsplit(chr(96)*3,1)[0].strip()
        try:answer=json.loads(content)
        except ValueError:answer={}
        return {"ok":True,"answer":answer,"seconds":round(time.perf_counter()-t,4),"usage":payload.get("usage",{}),"actual_model":payload.get("model"),"finish_reason":payload["choices"][0].get("finish_reason")}
    except urllib.error.HTTPError as e:return {"ok":False,"http_status":e.code}
    except Exception as e:return {"ok":False,"error":type(e).__name__}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--models",default="gh/gpt-4o-mini;nvidia/nvidia/nemotron-3-ultra-550b-a55b")
    p.add_argument("--scale",type=int,default=18)
    p.add_argument("--out",default="discovery-results")
    p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    if not 0<=a.scale<=50:p.error("Invalid scale")
    output=Path(a.out);output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);fixture(root,a.scale)
        ix=index_project(root)
        if ix["index_state"]!="CURRENT":raise RuntimeError("Index not current")
        build_relationships(root)
        all_entries=entries(root)
        baseline="\n\n".join("## "+p.relative_to(root).as_posix()+"\n"+p.read_text(encoding="utf8") for p in sorted(root.rglob("*.py")) if ".pie" not in p.parts)
        cases=tasks();contexts={};audit=[]
        for case in cases:
            started=time.perf_counter()
            pie,hit=retrieve(case,all_entries)
            audit.append({"id":case["id"],"hit":hit,"retrieval_seconds":round(time.perf_counter()-started,6),"pie_chars":len(pie),"baseline_chars":len(baseline)})
            contexts[case["id"]]={"pie":pie,"baseline":baseline}
        (output/"audit.json").write_text(json.dumps({"tasks":cases,"audit":audit},indent=2))
        print("AUDIT",json.dumps({"tasks":len(cases),"hits":sum(x["hit"] for x in audit),"baseline_chars":len(baseline),"pie_median_chars":statistics.median(x["pie_chars"] for x in audit)}),flush=True)
        if a.dry_run:return
        base=os.getenv("PIE_API_BASE_URL","")
        key=os.getenv("PIE_API_KEY","")
        if not base.startswith("https://") or not key:raise RuntimeError("No gateway credentials")
        models=a.models.split(";")
        results=[]
        for model in models:
            jobs=[(case,mode) for case in cases for mode in ("baseline","pie")]
            random.Random(1002).shuffle(jobs)
            for case,mode in jobs:
                r=request(base,key,model,case,contexts[case["id"]][mode])
                row={"model":model,"task":case["id"],"kind":case["kind"],"mode":mode,
                     "correct":r.get("answer")==case["expected"],**r}
                results.append(row)
                (output/"results.json").write_text(json.dumps({"results":results},indent=2))
                print("RESULT",model,case["id"],mode,row["correct"],row["ok"],row.get("seconds"),flush=True)
                time.sleep(.25)
        sums=[]
        for model in models:
            for mode in ("baseline","pie"):
                xs=[r for r in results if r["model"]==model and r["mode"]==mode]
                ok=[r for r in xs if r["ok"]]
                sums.append({"model":model,"mode":mode,"tasks":len(xs),"completed":len(ok),
                             "correct":sum(r["correct"] for r in xs),
                             "prompt_tokens":sum(r.get("usage",{}).get("prompt_tokens",0) for r in ok),
                             "median_latency_s":round(statistics.median(r["seconds"] for r in ok),4) if ok else None})
        (output/"summary.json").write_text(json.dumps({"summary":sums,"limitations":"Synthetic task corpus; no executable code change scoring. No private source included."},indent=2))
        print("SUMMARY",json.dumps(sums),flush=True)
if __name__=="__main__":main()
