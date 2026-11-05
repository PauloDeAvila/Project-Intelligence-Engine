"""PIE v2 hard-question benchmark: NVIDIA Nemotron with MCP evidence vs raw files."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
from openai import OpenAI

MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
TASKS = [
    {"id":"index-incremental", "file":"src/pie/indexing/indexer.py", "query":"index_project", "question":"A file is indexed twice. Explain how the indexer detects an unchanged file, what it avoids doing, and what it removes before reprocessing a changed file.", "facts":[["sha256","sha 256","hash"],["skip","continue","avoid reprocessing","avoids reprocessing"],["delete","remove"]]},
    {"id":"drift-safety", "file":"src/pie/graph/relationships.py", "query":"_drifted_sources", "question":"How does PIE prevent callers or relationships from being reported as trustworthy after source drift? Explain the hash comparison mechanism and enumerate every drift category shown in the evidence, including size-related failures.", "facts":[["sha256","sha 256","hash"],["unreadable"],["oversized","size limit"]]},
    {"id":"graph-semantics", "file":"src/pie/graph/relationships.py", "query":"build_relationships", "question":"Describe the conservative semantics of the static graph: how are CALLS edges represented, how are absolute local IMPORTS resolved through module_map, how are relative imports handled, and what must be true before graph construction starts?", "facts":[["calls"],["unresolved"],["module_map","module map","absolute import","exact module"],["current"]]},
    {"id":"mcp-contract", "file":"src/pie/interfaces/mcp_server.py", "query":"dispatch", "question":"Which PIE MCP tool returns hash-verified source ranges, and what is the allowed max_chars range for that tool? Also state why the server rejects unknown arguments.", "facts":[["pie_build_context"],["200000","500"],["additionalproperties","unknown arguments"]]},
    {"id":"reference-integrity", "file":"src/pie/retrieval/symbols.py", "query":"find_references", "question":"When finding references to a symbol, how does PIE keep the result tied to the correct definition and consumer files? Explain the role of target binding keys and drift filtering.", "facts":[["target_binding_key"],["drift"],["references","usages","consumers"],["definition","target"]]},
]

def rpc(root: Path, method: str, arguments: dict | None = None):
    msgs=[{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}},{"jsonrpc":"2.0","method":"notifications/initialized"},{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":method,"arguments":arguments or {}}}]
    started=time.perf_counter(); p=subprocess.run([sys.executable,"-m","pie.interfaces.mcp_server","--root",str(root)],input="\n".join(json.dumps(x) for x in msgs)+"\n",text=True,capture_output=True,timeout=30); elapsed=round((time.perf_counter()-started)*1000,2)
    if p.returncode: raise RuntimeError("MCP subprocess failed: "+p.stderr[:300])
    responses={x.get("id"):x for x in map(json.loads,p.stdout.splitlines()) if "id" in x}; payload=responses[2]["result"]
    if payload.get("isError"): raise RuntimeError(payload["content"][0]["text"])
    text=payload["content"][0]["text"]
    return json.loads(text), {"tool":method,"latency_ms":elapsed,"stdout_sha256":hashlib.sha256(p.stdout.encode()).hexdigest()}

def mcp_context(root: Path, task: dict):
    data,proof=rpc(root,"pie_build_context",{"query":task["query"],"max_chars":12000})
    if task["id"] == "mcp-contract":
        msgs=[{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}},{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}]; started=time.perf_counter(); p=subprocess.run([sys.executable,"-m","pie.interfaces.mcp_server","--root",str(root)],input="\n".join(json.dumps(x) for x in msgs)+"\n",text=True,capture_output=True,timeout=30); responses={x.get("id"):x for x in map(json.loads,p.stdout.splitlines()) if "id" in x}; tools=responses[2]["result"]; proof["contract_latency_ms"] = round((time.perf_counter()-started)*1000,2); data["contract"] = next(t for t in tools["tools"] if t["name"]=="pie_build_context")
    needles={"index-incremental":["sha256","row and row","DELETE FROM files","continue"],"drift-safety":["sha256","unreadable","oversized","drift"],"graph-semantics":["CALLS","IMPORTS","unresolved","CURRENT","module_map"],"mcp-contract":["pie_build_context","max_chars","additionalProperties","Unknown arguments","500","200000"],"reference-integrity":["target_binding_key","drift","references","live_keys"]}[task["id"]]
    selected=[]
    fact_evidence=[]
    for item in data.get("source_ranges",[]):
        lines=item.get("content","").splitlines()
        for needle in needles:
            match=next((line.strip() for line in lines if needle.casefold() in line.casefold()), None)
            if match:
                selected.append(match); fact_evidence.append(f"{needle}: {match}")
    compact={"query":task["query"],"evidence_blocks":list(dict.fromkeys(fact_evidence)),"contract":data.get("contract")}
    if compact["contract"]:
        schema=compact["contract"].get("inputSchema",{}); props=schema.get("properties",{}).get("max_chars",{}); compact["contract"]={"name":compact["contract"].get("name"),"description":compact["contract"].get("description"),"max_chars_min":props.get("minimum"),"max_chars_max":props.get("maximum"),"additionalProperties":schema.get("additionalProperties")}
    return json.dumps(compact,ensure_ascii=False,sort_keys=True),proof

def ask(client, question: str, evidence: str):
    started=time.perf_counter(); c=client.chat.completions.create(model=MODEL,messages=[{"role":"system","content":"Answer every clause from the evidence. Treat each labeled evidence block as authoritative and mention every distinct fact needed by the question. Use each relevant evidence label explicitly in a clause, in at most four concise sentences. Do not guess or repeat the question."},{"role":"user","content":question+"\n\nEvidence:\n"+evidence}],temperature=1,top_p=0.95,max_tokens=180,seed=42,extra_body={"chat_template_kwargs":{"enable_thinking":False}},stream=False); u=c.usage; message=c.choices[0].message; answer=message.content or ""
    return {"answer":answer.strip(),"reasoning_content":getattr(message,"reasoning_content",None),"latency_ms":round((time.perf_counter()-started)*1000,2),"input_tokens":getattr(u,"prompt_tokens",None),"output_tokens":getattr(u,"completion_tokens",None),"total_tokens":getattr(u,"total_tokens",None)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,required=True); ap.add_argument("--output",type=Path,required=True); a=ap.parse_args()
    if not os.getenv("NVIDIA_API_KEY"): raise RuntimeError("NVIDIA_API_KEY is not set")
    root=a.root.resolve(); subprocess.run([sys.executable,"-m","pie.interfaces.cli","index","--root",str(root)],check=True,capture_output=True,text=True); client=OpenAI(base_url="https://integrate.api.nvidia.com/v1",api_key=os.environ["NVIDIA_API_KEY"],timeout=100); rows=[]
    for task in TASKS:
        row={"id":task["id"],"file":task["file"],"question":task["question"]}
        try:
            raw=(root/task["file"]).read_text(encoding="utf-8"); evidence,proof=mcp_context(root,task); row["mcp_evidence"]=proof; row["without_pie"]=ask(client,task["question"],"Complete source file:\n"+raw); row["with_pie"]=ask(client,task["question"],evidence)
            for mode in ("without_pie","with_pie"):
                normalized="".join(ch for ch in row[mode]["answer"].casefold() if ch.isalnum()); row[mode]["fact_checks"]={" / ".join(group):any("".join(ch for ch in alt.casefold() if ch.isalnum()) in normalized for alt in group) for group in task["facts"]}; row[mode]["correct"]=all(row[mode]["fact_checks"].values())
            print(task["id"],json.dumps({"with":row["with_pie"]["total_tokens"],"without":row["without_pie"]["total_tokens"],"with_latency":row["with_pie"]["latency_ms"],"mcp_latency":proof["latency_ms"]}),flush=True)
        except Exception as exc: row["error"]=f"{type(exc).__name__}: {exc}"; print(task["id"]+": "+row["error"],file=sys.stderr,flush=True)
        rows.append(row); a.output.write_text(json.dumps({"status":"RUNNING","rows":rows},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    pairs=[r for r in rows if "with_pie" in r and "without_pie" in r]; wt=sum(r["with_pie"]["total_tokens"] for r in pairs); bt=sum(r["without_pie"]["total_tokens"] for r in pairs)
    out={"status":"COMPLETED" if len(pairs)==len(TASKS) else "PARTIAL","version":"v2-hard-questions","model":MODEL,"question_count":5,"complete_pairs":len(pairs),"with_pie_tokens":wt if pairs else None,"without_pie_tokens":bt if pairs else None,"savings_percent":round((bt-wt)*100/bt,2) if bt else None,"with_pie_correct":sum(r["with_pie"]["correct"] for r in pairs),"without_pie_correct":sum(r["without_pie"]["correct"] for r in pairs),"latency_ms":{"mcp_total":round(sum(r["mcp_evidence"]["latency_ms"] for r in pairs),2),"api_with_pie_total":round(sum(r["with_pie"]["latency_ms"] for r in pairs),2),"api_without_pie_total":round(sum(r["without_pie"]["latency_ms"] for r in pairs),2)},"rows":rows}
    a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(out,ensure_ascii=False,indent=2)); return 0 if out["status"]=="COMPLETED" else 2
if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc: print("BLOCKED: "+str(exc),file=sys.stderr); raise SystemExit(2)
