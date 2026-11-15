"""Fail-closed Codex real token accounting. Never persist prompts, answers or traces."""
from __future__ import annotations
import hashlib,json,math,os,shutil,subprocess,time,tomllib
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
    usage=[];answer="";calls=0;failed=False;mcp_tools=[]
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
                if e["type"]=="item.completed" and item.get("type")=="mcp_tool_call":
                    server=item.get("server");tool=item.get("tool");status=item.get("status")
                    if all(isinstance(v,str) for v in (server,tool,status)):
                        mcp_tools.append({"server":server[:120],"tool":tool[:120],"status":status[:40]})
                if e["type"]=="item.started" and item.get("type") in ("command_execution","mcp_tool_call","web_search","file_change"):
                    calls+=1
    if failed or len(usage)!=1:raise ValueError("Need one successful turn.completed event")
    return {"usage":usage[0],"answer":answer,"answer_sha256":_sha(answer),
            "tool_events":calls,"mcp_tools":mcp_tools,
            "source":"codex_exec_json_turn_completed","provider_reported":True}

def validate_scenario(s:dict)->dict:
    allowed={"scenario_id","prompt","expected_exact","model","description","required_mcp_server"}
    if not isinstance(s,dict) or set(s)-allowed:
        raise ValueError("Invalid scenario fields")
    if any(not isinstance(s.get(k),str) or not s[k].strip() for k in ("scenario_id","prompt","expected_exact","model")):
        raise ValueError("Scenario needs ID, prompt, expected exact answer, model")
    if "CONFIGURE_BEFORE_USE" in s["model"] or len(s["prompt"])>12000 or len(s["expected_exact"])>4000:
        raise ValueError("Unconfigured or oversized scenario")
    return s

def _auth_state(home:Path, executable:str, env:dict)->str:
    """Return a sanitized auth state; never expose auth material or output."""
    for name in ("OPENAI_API_KEY","CODEX_ACCESS_TOKEN"):
        if env.get(name):
            return "AUTH_PRESENT_ENV"
    auth=home/"auth.json"
    if not auth.is_file() or auth.stat().st_size==0:
        return "AUTH_MISSING"
    try:
        result=subprocess.run([executable,"login","status"],env=env,
                              capture_output=True,text=True,timeout=15,check=False)
    except (OSError,subprocess.TimeoutExpired):
        return "AUTH_UNAVAILABLE"
    # Do not persist or print stdout/stderr. A successful status command is
    # stronger evidence than file existence, but remains a local preflight.
    status_text=(result.stdout+"\n"+result.stderr).lower()
    if result.returncode==0 and "logged in" in status_text:
        return "AUTH_VALIDATED_LOCAL"
    return "AUTH_INVALID" if result.returncode==1 else "AUTH_UNAVAILABLE"

def preflight_codex(scenario:dict,*,condition:str,workspace:Path,codex_home:Path,
                    codex_bin:str="codex",evidence_dir:Path|None=None,
                    profile:str|None=None)->dict:
    """Run all non-model checks required before a paid Codex capture."""
    checks={};errors=[]
    try:scenario=validate_scenario(scenario);checks["scenario"]="PASS"
    except ValueError as exc:checks["scenario"]="FAIL";errors.append("PRECHECK_SCENARIO_INVALID");return {"state":"BLOCKED","checks":checks,"errors":errors}
    if condition not in CONDITIONS:checks["condition"]="FAIL";errors.append("PRECHECK_CONFIG_INVALID")
    else:checks["condition"]="PASS"
    workspace=Path(workspace).expanduser().resolve()
    codex_home=Path(codex_home).expanduser().resolve()
    try:
        commit=_git_clean_commit(workspace);checks["worktree"]={"state":"PASS","commit":commit}
    except (ValueError,OSError,subprocess.TimeoutExpired):
        checks["worktree"]={"state":"FAIL"};errors.append("PRECHECK_WORKTREE_DIRTY")
    config=codex_home/"config.toml"
    parsed=None
    try:
        parsed=tomllib.loads(config.read_text(encoding="utf-8"));checks["config"]="PASS"
    except (OSError,tomllib.TOMLDecodeError):
        checks["config"]="FAIL";errors.append("PRECHECK_CONFIG_INVALID")
    profile_parsed={}
    if profile is not None:
        profile_path=codex_home/(profile+".config.toml")
        try:
            if not profile or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in profile):
                raise ValueError("Invalid Codex profile")
            profile_parsed=tomllib.loads(profile_path.read_text(encoding="utf-8"));checks["profile"]="PASS"
        except (OSError,tomllib.TOMLDecodeError,ValueError):
            checks["profile"]="FAIL";errors.append("PRECHECK_CONFIG_INVALID")
    executable=shutil.which(codex_bin)
    if executable is None:checks["codex_executable"]="FAIL";errors.append("PRECHECK_AUTH_UNAVAILABLE")
    else:checks["codex_executable"]="PASS"
    if executable and parsed is not None:
        model=profile_parsed.get("model",parsed.get("model"))
        checks["model"]="PASS" if model==scenario["model"] else {"state":"FAIL","configured":model}
        if model!=scenario["model"]:errors.append("PRECHECK_MODEL_INVALID")
        servers=dict(parsed.get("mcp_servers") if isinstance(parsed.get("mcp_servers"),dict) else {})
        if isinstance(profile_parsed.get("mcp_servers"),dict):servers.update(profile_parsed["mcp_servers"])
        required=scenario.get("required_mcp_server")
        if required and required not in servers:
            checks["mcp"]={"state":"FAIL","required_server":required};errors.append("PRECHECK_MCP_UNAVAILABLE")
        else:
            checks["mcp"]={"state":"PASS","required_server":required}
            selected=servers.get(required) if required else None
            args=selected.get("args",[]) if isinstance(selected,dict) else []
            if not isinstance(args,list) or not all(isinstance(v,str) for v in args):
                checks["gateway_workspace"]="FAIL";errors.append("PRECHECK_CONFIG_INVALID")
            elif "pie.gateway.domain" in args and "--workspace" in args:
                pos=args.index("--workspace")
                configured=Path(args[pos+1]).expanduser().resolve() if pos+1<len(args) else None
                if configured != workspace:
                    checks["gateway_workspace"]={"state":"FAIL","reason":"MCP gateway workspace differs from Codex workspace"}
                    errors.append("PRECHECK_GATEWAY_WORKSPACE_MISMATCH")
                else: checks["gateway_workspace"]="PASS"
            else:
                checks["gateway_workspace"]="NOT_APPLICABLE"
        auth_env=dict(os.environ);auth_env["CODEX_HOME"]=str(codex_home)
        auth=_auth_state(codex_home,executable,auth_env)
        checks["authentication"]={"state":auth}
        if auth not in ("AUTH_VALIDATED_LOCAL","AUTH_PRESENT_ENV"):errors.append("PRECHECK_AUTH_MISSING" if auth=="AUTH_MISSING" else "PRECHECK_AUTH_UNAVAILABLE")
    if evidence_dir is not None:
        try:
            Path(evidence_dir).mkdir(parents=True,exist_ok=True)
            checks["evidence_dir"]="PASS"
        except OSError:
            checks["evidence_dir"]="FAIL";errors.append("PRECHECK_CONFIG_INVALID")
    return {"state":"READY_FOR_BENCHMARK" if not errors else "BLOCKED",
            "checks":checks,"errors":sorted(set(errors)),"model":scenario.get("model"),
            "condition":condition}

def _codex_environment(home:Path,profile:str|None=None):
    home=home.expanduser().resolve(strict=True)
    config=home/"config.toml"
    if not config.is_file():raise ValueError("CODEX_HOME/config.toml absent")
    hook=home/"hooks.json"
    material=config.read_bytes()+b"\0"+(hook.read_bytes() if hook.is_file() else b"")
    if profile is not None:
        if not profile or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in profile):
            raise ValueError("Invalid Codex profile")
        profile_path=home/(profile+".config.toml")
        if not profile_path.is_file():raise ValueError("Codex profile config absent")
        material+=b"\0"+profile_path.read_bytes()
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

def _expected_mcp_server(scenario:dict,condition:str)->str|None:
    required=scenario.get("required_mcp_server")
    if not isinstance(required,str):return None
    lowered=required.lower()
    if "blender" in lowered:return "blender" if condition=="baseline" else "pie-blender-optimized"
    if "web" in lowered or "playwright" in lowered:
        return "playwright-baseline" if condition=="baseline" else "pie-web-optimized"
    return required

def capture_codex(scenario,*,condition,repetition,workspace,codex_home,timeout=240,codex_bin="codex",profile=None):
    validate_scenario(scenario)
    if condition not in CONDITIONS or type(repetition) is not int or repetition<1:
        raise ValueError("Invalid condition or repetition")
    if type(timeout) is not int or not 20<=timeout<=3600:raise ValueError("Invalid timeout")
    workspace=Path(workspace).expanduser().resolve(strict=True)
    commit=_git_clean_commit(workspace)
    env,configsha=_codex_environment(Path(codex_home),profile=profile)
    telemetry_store=workspace/".pie-live-store"
    telemetry_store.mkdir(parents=True,exist_ok=True)
    env["PIE_GLOBAL_STORAGE_ROOT"]=str(telemetry_store)
    env["PIE_MCP_DIAGNOSTICS_PATH"]=str(telemetry_store/"mcp-lifecycle.jsonl")
    preflight=preflight_codex(scenario,condition=condition,workspace=workspace,
                              codex_home=Path(codex_home),codex_bin=codex_bin,profile=profile)
    if preflight["state"]!="READY_FOR_BENCHMARK":
        raise RuntimeError(preflight["errors"][0] if preflight["errors"] else "PRECHECK_CONFIG_INVALID")
    executable=shutil.which(codex_bin)
    if executable is None:raise RuntimeError("Codex executable unavailable")
    ver=subprocess.run([executable,"--version"],capture_output=True,text=True,timeout=10,check=False)
    if ver.returncode or not ver.stdout.strip():raise RuntimeError("Codex version unavailable")
    version=ver.stdout.strip().splitlines()[0][:120]
    args=[executable,"exec","--json","--ephemeral","--sandbox","read-only",
          "--cd",str(workspace),"--model",scenario["model"]]
    if profile is not None:args += ["--profile",profile]
    args += ["-"]
    t0=time.perf_counter()
    try:run=subprocess.run(args,cwd=workspace,env=env,input=scenario["prompt"],
                           text=True,capture_output=True,timeout=timeout,check=False)
    except (FileNotFoundError,subprocess.TimeoutExpired) as ex:
        raise RuntimeError("Codex execution unavailable/timeout") from ex
    if run.returncode:raise RuntimeError(f"Codex failed with exit code {run.returncode}; no certification")
    parsed=parse_codex_jsonl(run.stdout)
    expected_server=_expected_mcp_server(scenario,condition)
    if not parsed["mcp_tools"]:
        raise RuntimeError("MCP route evidence unavailable; no mcp_tool_call records")
    if expected_server is not None and any(
        item.get("server")!=expected_server or item.get("status")!="completed"
        for item in parsed["mcp_tools"]):
        observed=";".join("/".join(str(item.get(k,"")) for k in ("server","tool","status"))
                          for item in parsed["mcp_tools"])
        raise RuntimeError(f"MCP route evidence failed; expected {expected_server}; observed {observed}")
    actual=parsed.pop("answer").strip();expected=scenario["expected_exact"].strip()
    return {"schema":SCHEMA,"condition":condition,"scenario_id":scenario["scenario_id"],
            "repetition":repetition,"model":scenario["model"],"codex_version":version,
            "prompt_sha256":_sha(scenario["prompt"]),"expected_sha256":_sha(expected),
            "answer_sha256":_sha(actual),"oracle_kind":"exact_text","oracle_pass":actual==expected,
            "workspace_commit":commit,"configuration_sha256":configsha,"profile":profile,
            "runtime_ms":round((time.perf_counter()-t0)*1000,3),
            "tool_events":parsed["tool_events"],"mcp_tools":parsed["mcp_tools"],"usage":parsed["usage"],
            "expected_mcp_server":expected_server,"mcp_route_verified":True,
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
    for k in ("scenario_id","model","codex_version","prompt_sha256","expected_sha256","workspace_commit","configuration_sha256","expected_mcp_server"):
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
    tools=r.get("mcp_tools")
    if r.get("mcp_route_verified") is not True or not isinstance(tools,list) or not tools:
        raise ValueError("Missing verified MCP route evidence")
    if any(not isinstance(item,dict) or item.get("server")!=r["expected_mcp_server"] or
           item.get("status")!="completed" for item in tools):
        raise ValueError("MCP route/server/status mismatch")
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
