"""Fail-closed Codex real token accounting. Never persist prompts, answers or traces."""
from __future__ import annotations
import hashlib,json,math,os,shutil,subprocess,time
from pathlib import Path

SCHEMA="pie-live-codex-usage-v1"
CONDITIONS=frozenset(("baseline","optimized"))
def _sha(v):
    return hashlib.sha256(v if isinstance(v,bytes) else v.encode("utf-8")).hexdigest()
def _count(x,k):
    if type(x) is not int or x<0: raise ValueError("Missing/invalid provider "+k)
    return x

def parse_codex_jsonl(source:str)->dict:
    if not isinstance(source,str) or len(source.encode("utf-8"))>16_000_000:
        raise ValueError("Trace missing or too large")
    usage=[];answer="";calls=0;failed=False
    for line in source.splitlines():
        if not line.strip():continue
        try:e=json.loads(line)
        except json.JSONDecodeError as ex:raise ValueError("Malformed Codex JSONL") from ex
        if not isinstance(e,dict):raise ValueError("Invalid JSONL event")
        if e.get("type")=="turn.completed":
            u=e.get("usage")
            if not isinstance(u,dict):raise ValueError("Missing provider usage")
            row={k:_count(u.get(k),k) for k in ("input_tokens","cached_input_tokens","output_tokens")}
            row["reasoning_output_tokens"]=_count(u.get("reasoning_output_tokens",0),"reasoning_output_tokens")
            if row["cached_input_tokens"]>row["input_tokens"] or row["reasoning_output_tokens"]>row["output_tokens"]:
                raise ValueError("Incoherent provider usage")
            usage.append(row)
        elif e.get("type") in ("turn.failed","error"):failed=True
        elif e.get("type") in ("item.started","item.completed"):
            item=e.get("item")
            if isinstance(item,dict):
                if e["type"]=="item.completed" and item.get("type")=="agent_message" and isinstance(item.get("text"),str):
                    answer=item["text"]
                if e["type"]=="item.started" and item.get("type") in ("command_execution","mcp_tool_call","web_search","file_change"):
                    calls+=1
    if failed or len(usage)!=1:raise ValueError("Need one successful turn.completed event")
    return {"usage":usage[0],"answer":answer,"answer_sha256":_sha(answer),
            "tool_events":calls,"source":"codex_exec_json_turn_completed","provider_reported":True}

def validate_scenario(s:dict)->dict:
    if not isinstance(s,dict) or set(s)-{"scenario_id","prompt","expected_exact","model","description"}:
        raise ValueError("Invalid scenario fields")
    if any(not isinstance(s.get(k),str) or not s[k].strip() for k in ("scenario_id","prompt","expected_exact","model")):
        raise ValueError("Scenario needs ID, prompt, expected exact answer, model")
    if "CONFIGURE_BEFORE_USE" in s["model"] or len(s["prompt"])>12000 or len(s["expected_exact"])>4000:
        raise ValueError("Unconfigured or oversized scenario")
    return s

def _codex_environment(home:Path):
    home=home.expanduser().resolve(strict=True)
    config=home/"config.toml"
    if not config.is_file():raise ValueError("CODEX_HOME/config.toml absent")
    hook=home/"hooks.json"
    material=config.read_bytes()+b"\0"+(hook.read_bytes() if hook.is_file() else b"")
    env=dict(os.environ);env["CODEX_HOME"]=str(home)
    return env,_sha(material)

def _git_clean_commit(root:Path)->str:
    if not root.is_dir():raise ValueError("Workspace missing")
    def git(*args):
        r=subprocess.run(["git",*args],cwd=root,text=True,capture_output=True,timeout=20,check=False)
        if r.returncode:raise ValueError("Workspace is not a git checkout")
        return r.stdout.strip()
    sha=git("rev-parse","HEAD")
    if len(sha)!=40 or git("status","--porcelain","--untracked-files=all"):
        raise ValueError("Benchmark needs a clean immutable Git checkout")
    return sha

def capture_codex(scenario,*,condition,repetition,workspace,codex_home,timeout=240,codex_bin="codex"):
    validate_scenario(scenario)
    if condition not in CONDITIONS or type(repetition) is not int or repetition<1:
        raise ValueError("Invalid condition or repetition")
    if type(timeout) is not int or not 20<=timeout<=3600:raise ValueError("Invalid timeout")
    workspace=Path(workspace).expanduser().resolve(strict=True)
    commit=_git_clean_commit(workspace)
    env,configsha=_codex_environment(Path(codex_home))
    executable=shutil.which(codex_bin)
    if executable is None:raise RuntimeError("Codex executable unavailable")
    ver=subprocess.run([executable,"--version"],capture_output=True,text=True,timeout=10,check=False)
    if ver.returncode or not ver.stdout.strip():raise RuntimeError("Codex version unavailable")
    version=ver.stdout.strip().splitlines()[0][:120]
    args=[executable,"exec","--json","--ephemeral","--sandbox","read-only",
          "--cd",str(workspace),"--model",scenario["model"],"-"]
    t0=time.perf_counter()
    try:run=subprocess.run(args,cwd=workspace,env=env,input=scenario["prompt"],
                           text=True,capture_output=True,timeout=timeout,check=False)
    except (FileNotFoundError,subprocess.TimeoutExpired) as ex:
        raise RuntimeError("Codex execution unavailable/timeout") from ex
    if run.returncode:raise RuntimeError("Codex failed; inspect locally; no certification")
    parsed=parse_codex_jsonl(run.stdout)
    actual=parsed.pop("answer").strip();expected=scenario["expected_exact"].strip()
    return {"schema":SCHEMA,"condition":condition,"scenario_id":scenario["scenario_id"],
            "repetition":repetition,"model":scenario["model"],"codex_version":version,
            "prompt_sha256":_sha(scenario["prompt"]),"expected_sha256":_sha(expected),
            "answer_sha256":_sha(actual),"oracle_kind":"exact_text","oracle_pass":actual==expected,
            "workspace_commit":commit,"configuration_sha256":configsha,
            "runtime_ms":round((time.perf_counter()-t0)*1000,3),
            "tool_events":parsed["tool_events"],"usage":parsed["usage"],
            "provider_reported":parsed["provider_reported"],"source":parsed["source"],
            "note":"Codex provider usage, not billing or a raw transcript"}

def _read_records(paths:list[Path])->list[dict]:
    out=[]
    for path in paths:
        obj=json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj,list):out+=obj
        elif isinstance(obj,dict):out.append(obj)
        else:raise ValueError("Invalid record file")
    return out

def _record(r):
    if not isinstance(r,dict) or r.get("schema")!=SCHEMA or r.get("provider_reported") is not True or r.get("source")!="codex_exec_json_turn_completed":
        raise ValueError("No provider-reported usage evidence")
    if r.get("condition") not in CONDITIONS or r.get("oracle_kind")!="exact_text" or type(r.get("oracle_pass")) is not bool:
        raise ValueError("Condition/oracle absent")
    for k in ("scenario_id","model","codex_version","prompt_sha256","expected_sha256","workspace_commit","configuration_sha256"):
        if not isinstance(r.get(k),str) or not r[k]:raise ValueError("Missing "+k)
    if type(r.get("repetition")) is not int or r["repetition"]<1:raise ValueError("Invalid repetition")
    if type(r.get("tool_events")) is not int or r["tool_events"]<0:raise ValueError("Invalid tool count")
    u=r.get("usage")
    if not isinstance(u,dict):raise ValueError("No usage")
    inputs=_count(u.get("input_tokens"),"input_tokens")
    cached=_count(u.get("cached_input_tokens"),"cached_input_tokens")
    _count(u.get("output_tokens"),"output_tokens")
    if cached>inputs:raise ValueError("Cached input exceeds input")
    ms=r.get("runtime_ms")
    if isinstance(ms,bool) or not isinstance(ms,(float,int)) or not math.isfinite(ms) or ms<0:
        raise ValueError("Invalid runtime")
    return r["scenario_id"],r["repetition"]

def compare(records:list[dict],*,min_pairs=3,prices=None)->dict:
    if type(min_pairs) is not int or not 1<=min_pairs<=1000:raise ValueError("Invalid min_pairs")
    pairs={}
    try:
        for r in records:
            key=_record(r)
            group=pairs.setdefault(key,{})
            if r["condition"] in group:raise ValueError("Duplicate arm")
            group[r["condition"]]=r
        if len(pairs)<min_pairs:raise ValueError("Not enough paired samples")
        for arms in pairs.values():
            if set(arms)!=CONDITIONS:raise ValueError("Missing paired condition")
            a,b=arms["baseline"],arms["optimized"]
            for k in ("model","codex_version","prompt_sha256","expected_sha256","workspace_commit"):
                if a[k]!=b[k]:raise ValueError("Mismatched "+k)
            if a["configuration_sha256"]==b["configuration_sha256"]:
                raise ValueError("Same configuration; no attribution to PIE")
        if len({x["baseline"]["model"] for x in pairs.values()})!=1:raise ValueError("Multiple models")
        if not all(r["tool_events"]>0 for arms in pairs.values() for r in arms.values()):
            raise ValueError("No tool calls observed; no interception effect demonstrated")
        if not all(r["oracle_pass"] for arms in pairs.values() for r in arms.values()):
            raise ValueError("Accuracy oracle failed")
    except (ValueError,KeyError,TypeError) as ex:
        return {"state":"NOT_CERTIFIED","reason":str(ex),"pairs":len(pairs),
                "provider_tokens_measured":False,"savings_percent":None}
    totals={}
    for arm in sorted(CONDITIONS):
        vals=[v[arm] for _,v in sorted(pairs.items())]
        inp=sum(x["usage"]["input_tokens"] for x in vals)
        cache=sum(x["usage"]["cached_input_tokens"] for x in vals)
        out=sum(x["usage"]["output_tokens"] for x in vals)
        totals[arm]={"input_tokens":inp,"cached_input_tokens":cache,"uncached_input_tokens":inp-cache,
                     "output_tokens":out,"total_tokens":inp+out,
                     "duration_ms":sum(x["runtime_ms"] for x in vals),
                     "correct":len(vals),"tool_events":sum(x["tool_events"] for x in vals)}
    a,b=totals["baseline"],totals["optimized"]
    if a["input_tokens"]==0:
        return {"state":"NOT_CERTIFIED","reason":"Zero baseline tokens","pairs":len(pairs),
                "provider_tokens_measured":False,"savings_percent":None}
    result={"state":"REAL_PROVIDER_TOKENS_COMPARED","pairs":len(pairs),
            "provider_tokens_measured":True,"usage_source":"codex_exec_json_turn_completed",
            "quality_oracle":"exact_text_all_pass","totals":totals,
            "savings_percent":round(100*(1-b["input_tokens"]/a["input_tokens"]),3),
            "total_token_savings_percent":round(100*(1-b["total_tokens"]/a["total_tokens"]),3),
            "cached_input_delta":b["cached_input_tokens"]-a["cached_input_tokens"],
            "attribution_limit":"Config differs; real routing and confounders need independent audit"}
    if prices is None:result["estimated_usd"]=None
    else:
        fields={"input_per_million","cached_input_per_million","output_per_million"}
        if not isinstance(prices,dict) or set(prices)!=fields or any(
           isinstance(prices[k],bool) or not isinstance(prices[k],(int,float)) or
           not math.isfinite(prices[k]) or prices[k]<0 for k in fields):
            raise ValueError("Explicit valid USD per-million tariffs required")
        result["estimated_usd"]={name:round((v["uncached_input_tokens"]*prices["input_per_million"]+
           v["cached_input_tokens"]*prices["cached_input_per_million"]+
           v["output_tokens"]*prices["output_per_million"])/1e6,6) for name,v in totals.items()}
        result["cost_note"]="Tariff estimate only; not invoice or subscription consumption"
    return result
