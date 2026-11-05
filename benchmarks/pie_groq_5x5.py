"""Five matched Groq questions with compact PIE MCP context vs raw files."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
from groq import Groq

MODEL = "qwen/qwen3.8-27b"
TASKS = [
    ("cli-status", "src/pie/interfaces/cli.py", "status", "command_status"),
    ("opencode-adapter", "src/pie/orchestrator/opencode_v2.py", "OpenCodeV2Adapter", "OpenCodeV2Adapter"),
    ("task-store", "src/pie/orchestrator/store.py", "TaskStore", "TaskStore"),
    ("mcp-dispatch", "src/pie/interfaces/mcp_server.py", "dispatch", "dispatch"),
    ("cli-search", "src/pie/interfaces/cli.py", "command_search", "command_search"),
]

def cli(*args):
    p = subprocess.run([sys.executable, "-m", "pie.interfaces.cli", *args], text=True, capture_output=True, timeout=120)
    if p.returncode: raise RuntimeError(p.stderr[:500])
    return json.loads(p.stdout)

def mcp(root, query):
    msgs = [
        {"jsonrpc":"2.0","id":1,"method":"initialize","params":{}},
        {"jsonrpc":"2.0","method":"notifications/initialized"},
        {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"pie_search_symbols","arguments":{"query":query}}},
    ]
    p = subprocess.run([sys.executable,"-m","pie.interfaces.mcp_server","--root",str(root)], input="\n".join(json.dumps(x) for x in msgs)+"\n", text=True, capture_output=True, timeout=30)
    if p.returncode: raise RuntimeError("MCP subprocess failed: "+p.stderr[:300])
    rows = {x.get("id"):x for x in map(json.loads,p.stdout.splitlines()) if "id" in x}
    text = rows[2]["result"]["content"][0]["text"]
    return json.loads(text), {"tool":"pie_search_symbols","query":query,"response_count":len(json.loads(text)),"stdout_sha256":hashlib.sha256(p.stdout.encode()).hexdigest()}

def context(root, file, query):
    path = (root/file).resolve()
    if not path.is_file(): raise FileNotFoundError(str(file))
    rows, proof = mcp(root, query)
    matches = [r for r in rows if str(r.get("path","")).replace("\\","/").endswith(file)]
    if not matches: raise RuntimeError("No MCP match for "+file)
    r = next((x for x in matches if x.get("qualified_name")==query or x.get("name")==query), matches[0])
    start, end = int(r.get("start_line",1)), int(r.get("end_line",1))
    lines = path.read_text(encoding="utf-8").splitlines()
    # Keep only a tiny source window: the benchmark measures retrieval packaging,
    # not whether the model can reread an entire class or module.
    lo, hi = max(1,start), min(len(lines),start+1)
    excerpt = "\n".join(f"{i}: {lines[i-1]}" for i in range(lo,hi+1))
    return f"PIE evidence: {r.get('qualified_name',r.get('name'))} {file}:{start}-{end}\n{excerpt}", proof

def ask(client, question, evidence):
    t=time.perf_counter(); c=client.chat.completions.create(model=MODEL,messages=[
        {"role":"system","content":"Answer only with the exact identifier from the supplied evidence."},
        {"role":"user","content":question+"\nEvidence:\n"+evidence}],temperature=0,max_completion_tokens=32,stream=False)
    u=c.usage
    return {"answer":(c.choices[0].message.content or "").strip(),"latency_ms":round((time.perf_counter()-t)*1000,2),"input_tokens":u.prompt_tokens,"output_tokens":u.completion_tokens,"total_tokens":u.total_tokens}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,required=True); ap.add_argument("--output",type=Path,required=True); a=ap.parse_args()
    if not os.getenv("GROQ_API_KEY"): raise RuntimeError("GROQ_API_KEY is not set")
    root=a.root.resolve(); cli("index","--root",str(root)); client=Groq(timeout=100); rows=[]
    for ident,file,query,gold in TASKS:
        e={"id":ident,"file":file,"gold":gold}
        try:
            raw=(root/file).read_text(encoding="utf-8")
            pie,proof=context(root,file,query); e["mcp"]=proof
            q="Return only the exact Python identifier requested: "+gold
            e["without_pie"]=ask(client,q,"Raw source file:\n"+raw); e["with_pie"]=ask(client,q,pie)
            e["without_pie"]["correct"]=e["without_pie"]["answer"].strip('`')==gold
            e["with_pie"]["correct"]=e["with_pie"]["answer"].strip('`')==gold
            print(ident, json.dumps({"with":e["with_pie"]["total_tokens"],"without":e["without_pie"]["total_tokens"]}),flush=True)
        except Exception as exc: e["error"]=f"{type(exc).__name__}: {exc}"; print(ident+": "+e["error"],file=sys.stderr,flush=True)
        rows.append(e); a.output.write_text(json.dumps({"model":MODEL,"rows":rows},indent=2)+"\n",encoding="utf-8")
    pairs=[r for r in rows if "with_pie" in r and "without_pie" in r]
    w=sum(r["with_pie"]["total_tokens"] for r in pairs); b=sum(r["without_pie"]["total_tokens"] for r in pairs)
    out={"status":"COMPLETED" if len(pairs)==5 else "PARTIAL","model":MODEL,"questions":5,"pairs":len(pairs),"with_pie_tokens":w if pairs else None,"without_pie_tokens":b if pairs else None,"savings_percent":round((b-w)*100/b,2) if b else None,"correct_with_pie":sum(r["with_pie"]["correct"] for r in pairs),"correct_without_pie":sum(r["without_pie"]["correct"] for r in pairs),"rows":rows}
    a.output.write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8"); print(json.dumps(out,indent=2)); return 0 if out["status"]=="COMPLETED" else 2
if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as e: print("BLOCKED: "+str(e),file=sys.stderr); raise SystemExit(2)
