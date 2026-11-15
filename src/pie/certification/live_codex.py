"""Fail-closed Codex real token accounting. Never persist prompts, answers or traces."""
from __future__ import annotations
import hashlib,json,math,os,re,shutil,subprocess,time,tomllib
from pathlib import Path
from datetime import datetime,timezone

SCHEMA="pie-live-codex-usage-v1"
CONDITIONS=frozenset(("baseline","optimized"))

class CodexCaptureError(RuntimeError):
    """Sanitized failure with non-certifying provider/tool evidence."""
    def __init__(self, message: str, *, evidence: dict | None = None):
        super().__init__(message)
        self.evidence = evidence or {}

def _sha(v):
    return hashlib.sha256(v if isinstance(v,bytes) else v.encode("utf-8")).hexdigest()

def _expected_mcp_tools(scenario:dict, condition:str)->list[str]|None:
    by_condition=scenario.get("expected_mcp_tools_by_condition")
    if isinstance(by_condition,dict):
        tools=by_condition.get(condition)
        return list(tools) if isinstance(tools,list) else None
    tools=scenario.get("expected_mcp_tools")
    return list(tools) if isinstance(tools,list) else None

def _observed_mcp_tools_match(scenario:dict, condition:str, observed:list[str])->bool:
    """Match required MCP calls while treating Web recovery as optional."""
    expected=_expected_mcp_tools(scenario,condition)
    if expected is None:
        return True
    if (condition == "optimized" and
        str(scenario.get("required_mcp_server", "")).lower() in ("web", "playwright") and
        "pie_gateway_output_get" in expected):
        required=[tool for tool in expected if tool != "pie_gateway_output_get"]
        return observed == required or observed == expected
    return observed == expected

def _enabled_mcp_servers(servers: dict) -> set[str]:
    return {name for name, value in servers.items()
            if isinstance(name, str) and
            (not isinstance(value, dict) or value.get("enabled", True) is not False)}

def _runtime_enabled_mcp_servers(executable: str, codex_home: Path, profile: str | None) -> set[str] | None:
    """Read Codex's effective MCP registry without starting a model session."""
    if not profile:
        return None
    env = dict(os.environ)
    env["CODEX_HOME"] = str(codex_home)
    try:
        result = subprocess.run([executable, "--profile", profile, "mcp", "list", "--json"],
                                env=env, capture_output=True, text=True, timeout=30, check=False)
        payload = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list):
        return None
    return {item["name"] for item in payload
            if isinstance(item, dict) and item.get("enabled") is True and isinstance(item.get("name"), str)}

def _utc_now():
    return datetime.now(timezone.utc).isoformat()

def _sanitize_text(value, *, limit=200_000):
    """Keep diagnostics useful without retaining credentials or transcripts."""
    text=value.decode("utf-8",errors="replace") if isinstance(value,bytes) else str(value or "")
    text=re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+", r"\1[REDACTED]", text)
    text=re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[REDACTED]", text)
    text=re.sub(r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|cookie|set-cookie)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text=re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED_KEY]", text)
    return text[:limit]

def _materialize_runtime_profile(home: Path, profile: str | None, *, server: str,
                                 runtime_env: dict[str, str], run_id: str) -> tuple[str | None, Path | None]:
    """Create an ephemeral profile that explicitly passes telemetry to one MCP server."""
    if profile is None:
        return None, None
    source = home / (profile + ".config.toml")
    if not source.is_file():
        # Keep mocked/offline capture boundaries compatible; real preflight still
        # rejects the absent profile before a model process can start.
        return profile, None
    text = source.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    servers = parsed.get("mcp_servers")
    if not isinstance(servers, dict) or server not in servers:
        raise ValueError("Expected MCP server absent from profile")
    header = f"[mcp_servers.{server}]"
    lines = text.splitlines()
    try:
        start = lines.index(header)
    except ValueError as exc:
        raise ValueError("Expected MCP server section absent from profile") from exc
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("[mcp_servers.") and lines[i].endswith("]")), len(lines))
    configured_env = ((parsed.get("mcp_servers") or {}).get(server) or {}).get("env", {})
    if not isinstance(configured_env, dict):
        raise ValueError("MCP server env must be a table")
    merged_env = {str(key): str(value) for key, value in configured_env.items()}
    merged_env.update({str(key): str(value) for key, value in runtime_env.items()})
    env = "env = { " + ", ".join(
        f"{key} = '{value.replace(chr(39), '')}'" for key, value in sorted(merged_env.items())
    ) + " }"
    replaced = False
    for index in range(start + 1, end):
        if lines[index].lstrip().startswith("env ="):
            lines[index] = env
            replaced = True
            break
    if not replaced:
        command_index = next((i for i in range(start + 1, end)
                              if lines[i].lstrip().startswith("command =")), None)
        if command_index is None:
            raise ValueError("MCP server command absent from profile")
        lines.insert(command_index + 1, env)
    effective = f"{profile}-run-{run_id}"
    destination = home / (effective + ".config.toml")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return effective, destination

def _forensic_dir(store:Path, run_id:str)->Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}",run_id):
        raise ValueError("Invalid forensic run_id")
    return store/"runs"/run_id

def _write_json(path:Path,value:dict):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def _forensic_start(store:Path, *, scenario:dict, condition:str, repetition:int,
                    run_id:str, pair_id:str, workspace_commit:str, configsha:str,
                    expected_server:str|None, profile:str|None)->Path:
    root=_forensic_dir(store,run_id)
    root.mkdir(parents=True,exist_ok=False)
    expected=scenario["expected_exact"].strip()
    _write_json(root/"manifest.json",{
        "schema":"pie-forensic-capture-v1","capture_status":"started",
        "created_at":_utc_now(),"run_id":run_id,"pair_id":pair_id,
        "scenario_id":scenario["scenario_id"],"condition":condition,
        "repetition":repetition,"application":_scenario_app(scenario),
        "model":scenario["model"],"profile":profile,
        "prompt_sha256":_sha(scenario["prompt"]),"expected_sha256":_sha(expected),
        "workspace_commit":workspace_commit,"configuration_sha256":configsha,
        "expected_mcp_server":expected_server,
        "expected_mcp_tools":_expected_mcp_tools(scenario,condition),
    })
    for name in ("codex-stdout.log","codex-stderr.log","codex-events.jsonl","mcp-tool-events.jsonl"):
        (root/name).write_text("",encoding="utf-8")
    _write_json(root/"provider-usage.json",{
        "schema":"pie-forensic-provider-usage-v1","run_id":run_id,
        "provider_usage_status":"unavailable","reason":"not_observed_yet"})
    _write_json(root/"oracle-result.json",{"status":"not_evaluated","run_id":run_id})
    _write_json(root/"run-result.json",{
        "schema":"pie-forensic-run-result-v1","run_id":run_id,"pair_id":pair_id,
        "status":"started","started_at":_utc_now()})
    return root

def _forensic_event(event:dict)->dict:
    item=event.get("item") if isinstance(event.get("item"),dict) else {}
    out={"event_type":_sanitize_text(event.get("type","unknown"),limit=80)}
    if isinstance(event.get("usage"),dict):
        usage=event["usage"]
        out["usage"]={k:usage[k] for k in ("input_tokens","cached_input_tokens","output_tokens","reasoning_output_tokens")
                      if type(usage.get(k)) is int and usage[k]>=0}
    if item:
        for key in ("type","server","tool","status"):
            value=item.get(key)
            if isinstance(value,str):out["item_"+key if key=="type" else key]=_sanitize_text(value,limit=120)
    return out

def _forensic_capture_process(root:Path, *, stdout, stderr, returncode, duration_ms, timed_out=False):
    events=[];mcp=[]
    source=_sanitize_text(stdout,limit=2_000_000)
    for line in source.splitlines():
        if not line.strip():continue
        try:
            event=json.loads(line)
            if not isinstance(event,dict):raise ValueError
            safe=_forensic_event(event);events.append(safe)
            if safe.get("event_type") == "item.completed" and safe.get("item_type") == "mcp_tool_call":
                mcp.append(safe)
        except (ValueError,json.JSONDecodeError):
            events.append({"type":"malformed","sha256":_sha(line),"length":len(line)})
    (root/"codex-stdout.log").write_text("\n".join(json.dumps(e,ensure_ascii=False) for e in events)+("\n" if events else ""),encoding="utf-8")
    (root/"codex-events.jsonl").write_text("\n".join(json.dumps(e,ensure_ascii=False) for e in events)+("\n" if events else ""),encoding="utf-8")
    (root/"mcp-tool-events.jsonl").write_text("\n".join(json.dumps(e,ensure_ascii=False) for e in mcp)+("\n" if mcp else ""),encoding="utf-8")
    (root/"codex-stderr.log").write_text(_sanitize_text(stderr),encoding="utf-8")
    usage=[]
    for event in events:
        value=event.get("usage")
        if isinstance(value,dict) and all(type(value.get(k)) is int and value[k]>=0 for k in ("input_tokens","cached_input_tokens","output_tokens")):
            usage.append(value)
    if len(usage)==1 and usage[0]["cached_input_tokens"]<=usage[0]["input_tokens"]:
        _write_json(root/"provider-usage.json",{
            "schema":"pie-forensic-provider-usage-v1","run_id":json.loads((root/"run-result.json").read_text(encoding="utf-8"))["run_id"],
            "provider_usage_status":"available","provider_reported":True,"usage":usage[0]})
    else:
        _write_json(root/"provider-usage.json",{
            "schema":"pie-forensic-provider-usage-v1","run_id":json.loads((root/"run-result.json").read_text(encoding="utf-8"))["run_id"],
            "provider_usage_status":"unavailable","reason":"missing_or_ambiguous_turn_completed_usage"})
    return len(events),len(mcp)

def _forensic_finish(root:Path, *, status:str, returncode=None, duration_ms=None, error=None, timed_out=False):
    path=root/"run-result.json"
    result=json.loads(path.read_text(encoding="utf-8"))
    result.update({"status":status,"finished_at":_utc_now(),"returncode":returncode,
                   "duration_ms":duration_ms,"timed_out":timed_out})
    if error:result["error"]=_sanitize_text(error,limit=2_000)
    _write_json(path,result)
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    manifest.update({"capture_status":status,"finished_at":result["finished_at"]})
    _write_json(root/"manifest.json",manifest)
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
                        mcp_tools.append({"server":_sanitize_text(server,limit=120),
                                          "tool":_sanitize_text(tool,limit=120),
                                          "status":_sanitize_text(status,limit=40)})
                if e["type"]=="item.started" and item.get("type") in ("command_execution","mcp_tool_call","web_search","file_change"):
                    calls+=1
    if failed or len(usage)!=1:raise ValueError("Need one successful turn.completed event")
    return {"usage":usage[0],"answer":answer,"answer_sha256":_sha(answer),
            "tool_events":calls,"mcp_tools":mcp_tools,
            "source":"codex_exec_json_turn_completed","provider_reported":True}

def validate_scenario(s:dict)->dict:
    allowed={"schema","scenario_id","prompt","expected_exact","model","description","required_mcp_server",
             "expected_mcp_tools","expected_mcp_tools_by_condition","oracle","task_id","application",
             "fixture_spec","reasoning_effort","conditions","constraints","experiment_type"}
    if not isinstance(s,dict) or set(s)-allowed:
        raise ValueError("Invalid scenario fields")
    if any(not isinstance(s.get(k),str) or not s[k].strip() for k in ("scenario_id","prompt","expected_exact","model")):
        raise ValueError("Scenario needs ID, prompt, expected exact answer, model")
    if "CONFIGURE_BEFORE_USE" in s["model"] or len(s["prompt"])>12000 or len(s["expected_exact"])>4000:
        raise ValueError("Unconfigured or oversized scenario")
    tools=s.get("expected_mcp_tools")
    if tools is not None:
        if (not isinstance(tools,list) or not tools or
            any(not isinstance(tool,str) or not tool.strip() for tool in tools) or
            len(set(tools)) != len(tools)):
            raise ValueError("Invalid expected MCP tool allowlist")
    by_condition=s.get("expected_mcp_tools_by_condition")
    if by_condition is not None:
        if (not isinstance(by_condition,dict) or set(by_condition)!={"baseline","optimized"} or
                any(not isinstance(value,list) or not value or
                    any(not isinstance(tool,str) or not tool.strip() for tool in value) or
                    len(set(value)) != len(value) for value in by_condition.values())):
            raise ValueError("Invalid condition-specific MCP tool allowlist")
    if "oracle" in s and (not isinstance(s["oracle"],dict) or not isinstance(s["oracle"].get("kind"),str)):
        raise ValueError("Invalid oracle specification")
    oracle=s.get("oracle")
    if isinstance(oracle,dict) and oracle.get("kind")=="blender_scene_json":
        expected=oracle.get("expected")
        required={"object_name","object_type","location","material_names"}
        if not isinstance(expected,dict) or set(expected)!=required:
            raise ValueError("Invalid Blender JSON oracle")
    return s

def _evaluate_answer(scenario:dict, actual:str)->tuple[bool,str]:
    oracle=scenario.get("oracle")
    if isinstance(oracle,dict) and oracle.get("kind")=="blender_scene_json":
        try:
            value=json.loads(actual)
        except (TypeError,json.JSONDecodeError):
            return False,"blender_scene_json"
        expected=oracle["expected"]
        if isinstance(value,dict) and isinstance(value.get("object_type"),str):
            value=dict(value)
            value["object_type"]=value["object_type"].upper()
        return value==expected,"blender_scene_json"
    return actual==scenario["expected_exact"].strip(),"exact_text"

def _oracle_diagnostic(scenario:dict, actual:str, passed:bool)->dict:
    """Record answer shape only; never persist answer values or transcripts."""
    diagnostic={"passed":bool(passed),"length":len(actual),"sha256":_sha(actual)}
    oracle=scenario.get("oracle")
    if not isinstance(oracle,dict) or oracle.get("kind")!="blender_scene_json":
        diagnostic["format"]="text"
        return diagnostic
    try:
        value=json.loads(actual)
    except (TypeError,json.JSONDecodeError):
        diagnostic["format"]="invalid_json"
        return diagnostic
    diagnostic["format"]="json"
    if not isinstance(value,dict):
        diagnostic["json_type"]=type(value).__name__
        return diagnostic
    expected=oracle.get("expected") if isinstance(oracle.get("expected"),dict) else {}
    diagnostic["keys"]=sorted(value)
    diagnostic["missing_keys"]=sorted(set(expected)-set(value))
    diagnostic["extra_keys"]=sorted(set(value)-set(expected))
    diagnostic["field_types"]={key:type(value[key]).__name__ for key in sorted(value)}
    for key in ("location","material_names"):
        if isinstance(value.get(key),list):
            diagnostic[f"{key}_length"]=len(value[key])
    return diagnostic

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
        required=_expected_mcp_server(scenario,condition) if scenario.get("required_mcp_server") else None
        enabled_servers = _enabled_mcp_servers(servers)
        if required and required not in enabled_servers:
            checks["mcp"]={"state":"FAIL","required_server":required};errors.append("PRECHECK_MCP_UNAVAILABLE")
        elif required and enabled_servers != {required}:
            checks["mcp"]={"state":"FAIL","required_server":required,"enabled_servers":sorted(enabled_servers)}
            errors.append("PRECHECK_MCP_ISOLATION_FAILED")
        else:
            checks["mcp"]={"state":"PASS","required_server":required}
            selected=servers.get(required) if required else None
            expected_tools = _expected_mcp_tools(scenario, condition)
            configured_tools = selected.get("enabled_tools") if isinstance(selected, dict) else None
            if expected_tools is not None and configured_tools != expected_tools:
                checks["mcp_tools"]={"state":"FAIL","expected":expected_tools,"configured":configured_tools}
                errors.append("PRECHECK_MCP_ISOLATION_FAILED")
            else:
                checks["mcp_tools"]={"state":"PASS","enabled_tools":configured_tools}
            command=selected.get("command") if isinstance(selected,dict) else None
            command_ok=(isinstance(command,str) and bool(command.strip()) and
                        (Path(command).is_file() if ("\\" in command or "/" in command)
                         else shutil.which(command) is not None))
            checks["mcp_command"]="PASS" if command_ok else {"state":"FAIL"}
            if not command_ok:
                errors.append("PRECHECK_MCP_COMMAND_UNAVAILABLE")
            if command_ok and isinstance(selected,dict) and "pie.gateway.domain" in (selected.get("args") or []):
                configured_env=selected.get("env",{})
                source_root=configured_env.get("PIE_SOURCE_ROOT") if isinstance(configured_env,dict) else None
                source_commit=configured_env.get("PIE_SOURCE_COMMIT") if isinstance(configured_env,dict) else None
                pythonpath=configured_env.get("PYTHONPATH") if isinstance(configured_env,dict) else None
                source_ok=False
                if isinstance(source_root,str) and isinstance(source_commit,str) and isinstance(pythonpath,str):
                    try:
                        source_path=Path(source_root).expanduser().resolve(strict=True)
                        source_ok=(source_path.is_dir() and Path(pythonpath).expanduser().resolve()==source_path)
                        git_root=source_path.parent
                        git_result=subprocess.run(["git","-C",str(git_root),"rev-parse","HEAD"],
                                                  capture_output=True,text=True,timeout=20,check=False)
                        source_ok=source_ok and git_result.returncode==0 and len(source_commit)==40
                        if source_ok:
                            source_tree=subprocess.run(["git","-C",str(git_root),"diff","--quiet",
                                                        source_commit,"HEAD","--","src"],
                                                       capture_output=True,timeout=20,check=False)
                            source_ok=source_tree.returncode==0
                        if source_ok:
                            probe_env=dict(os.environ);probe_env.update({"PYTHONPATH":str(source_path)})
                            probe=subprocess.run([command,"-c","import pie; print(pie.__file__)"],
                                                 env=probe_env,capture_output=True,text=True,timeout=20,check=False)
                            module_path=Path(probe.stdout.strip()).resolve() if probe.returncode==0 and probe.stdout.strip() else None
                            source_ok=module_path is not None and module_path.is_relative_to(source_path)
                    except (OSError,subprocess.SubprocessError,ValueError):
                        source_ok=False
                checks["pie_source"]="PASS" if source_ok else {"state":"FAIL"}
                if not source_ok:
                    errors.append("PRECHECK_PIE_SOURCE_INVALID")
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
        if executable and Path(executable).is_file() and "codex" in Path(executable).name.lower() and required:
            runtime_servers = _runtime_enabled_mcp_servers(executable, codex_home, profile)
            if runtime_servers is None:
                checks["mcp_runtime"]={"state":"FAIL"}
                errors.append("PRECHECK_MCP_ISOLATION_FAILED")
            elif runtime_servers != {required}:
                checks["mcp_runtime"]={"state":"FAIL","required_server":required,"enabled_servers":sorted(runtime_servers)}
                errors.append("PRECHECK_MCP_ISOLATION_FAILED")
            else:
                checks["mcp_runtime"]={"state":"PASS","enabled_servers":sorted(runtime_servers)}
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

def _telemetry_store(workspace:Path)->Path:
    return workspace.parent/("."+workspace.name+"-pie-live-store")

def _capture_run_id(scenario:dict,condition:str,repetition:int)->str:
    material="|".join((scenario["scenario_id"],condition,str(repetition)))
    return f"{condition}-{_sha(material)[:24]}"

def _capture_pair_id(scenario:dict)->str:
    return f"pair-{_sha(scenario['scenario_id'])[:24]}"

def _scenario_app(scenario:dict)->str:
    value=" ".join(str(scenario.get(k,"")) for k in ("required_mcp_server","scenario_id")).lower()
    if "blender" in value:return "blender"
    if "web" in value or "playwright" in value:return "web"
    return "other_mcp"

def _expected_mcp_server(scenario:dict,condition:str)->str|None:
    required=scenario.get("required_mcp_server")
    if not isinstance(required,str):return None
    lowered=required.lower()
    if lowered == "blender":return "blender" if condition=="baseline" else "pie-blender-optimized"
    if lowered in ("web", "playwright"):
        return "playwright-baseline" if condition=="baseline" else "pie-web-optimized"
    return required

def capture_codex(scenario,*,condition,repetition,workspace,codex_home,timeout=240,codex_bin="codex",profile=None,
                  run_id_override=None,pair_id_override=None):
    validate_scenario(scenario)
    if condition not in CONDITIONS or type(repetition) is not int or repetition<1:
        raise ValueError("Invalid condition or repetition")
    if type(timeout) is not int or not 20<=timeout<=3600:raise ValueError("Invalid timeout")
    workspace=Path(workspace).expanduser().resolve(strict=True)
    commit=_git_clean_commit(workspace)
    run_id=run_id_override or _capture_run_id(scenario,condition,repetition)
    pair_id=pair_id_override or _capture_pair_id(scenario)
    if (not isinstance(run_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}",run_id) or
        not isinstance(pair_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}",pair_id)):
        raise ValueError("Invalid capture identity")
    expected_server=_expected_mcp_server(scenario,condition)
    telemetry_store=_telemetry_store(workspace)
    telemetry_store.mkdir(parents=True,exist_ok=True)
    runtime_env={"PIE_RUN_ID":run_id,"PIE_PAIR_ID":pair_id,
                 "PIE_TASK_ID":scenario["scenario_id"],"PIE_CONDITION":condition,
                 "PIE_APP":_scenario_app(scenario),"PIE_SCENARIO_ID":scenario["scenario_id"],
                 "PIE_GATEWAY_SERVER":expected_server or "",
                 "PIE_GLOBAL_STORAGE_ROOT":str(telemetry_store),
                 "PIE_MCP_DIAGNOSTICS_PATH":str(telemetry_store / "mcp-lifecycle.jsonl")}
    effective_profile, _runtime_profile_path = _materialize_runtime_profile(
        Path(codex_home), profile, server=expected_server, runtime_env=runtime_env,
        run_id=run_id)
    env,configsha=_codex_environment(Path(codex_home),profile=effective_profile)
    env.update({"PIE_RUN_ID":run_id,"PIE_PAIR_ID":pair_id,
                "PIE_TASK_ID":scenario["scenario_id"],"PIE_CONDITION":condition,
                "PIE_APP":_scenario_app(scenario),"PIE_SCENARIO_ID":scenario["scenario_id"],
                "PIE_GATEWAY_SERVER":expected_server or ""})
    env["PIE_GLOBAL_STORAGE_ROOT"]=str(telemetry_store)
    env["PIE_MCP_DIAGNOSTICS_PATH"]=str(telemetry_store/"mcp-lifecycle.jsonl")
    forensic_root=_forensic_start(telemetry_store,scenario=scenario,condition=condition,
                                   repetition=repetition,run_id=run_id,pair_id=pair_id,
                                   workspace_commit=commit,configsha=configsha,
                                   expected_server=expected_server,profile=effective_profile)
    try:
        preflight=preflight_codex(scenario,condition=condition,workspace=workspace,
                                  codex_home=Path(codex_home),codex_bin=codex_bin,profile=effective_profile)
    except Exception as exc:
        _forensic_finish(forensic_root,status="preflight_failed",error=str(exc))
        raise
    if preflight["state"]!="READY_FOR_BENCHMARK":
        error=preflight["errors"][0] if preflight["errors"] else "PRECHECK_CONFIG_INVALID"
        _forensic_finish(forensic_root,status="preflight_failed",error=error)
        raise RuntimeError(error)
    executable=shutil.which(codex_bin)
    if executable is None:
        _forensic_finish(forensic_root,status="executor_failed",error="Codex executable unavailable")
        raise RuntimeError("Codex executable unavailable")
    try:ver=subprocess.run([executable,"--version"],capture_output=True,text=True,timeout=10,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        _forensic_finish(forensic_root,status="executor_failed",error="Codex version unavailable")
        raise RuntimeError("Codex version unavailable") from exc
    if ver.returncode or not ver.stdout.strip():
        _forensic_finish(forensic_root,status="executor_failed",error="Codex version unavailable")
        raise RuntimeError("Codex version unavailable")
    version=ver.stdout.strip().splitlines()[0][:120]
    args=[executable,"exec","--json","--ephemeral","--sandbox","read-only",
          "--cd",str(workspace),"--model",scenario["model"]]
    if effective_profile is not None:args += ["--profile",effective_profile]
    args += ["-"]
    t0=time.perf_counter()
    try:
        run=subprocess.run(args,cwd=workspace,env=env,input=scenario["prompt"],
                           text=True,capture_output=True,timeout=timeout,check=False)
    except subprocess.TimeoutExpired as ex:
        _forensic_capture_process(forensic_root,stdout=getattr(ex,"output","") or "",
                                  stderr=getattr(ex,"stderr","") or "",returncode=None,
                                  duration_ms=round((time.perf_counter()-t0)*1000,3),timed_out=True)
        _forensic_finish(forensic_root,status="timeout",duration_ms=round((time.perf_counter()-t0)*1000,3),
                         error="Codex execution timeout",timed_out=True)
        raise RuntimeError("Codex execution unavailable/timeout") from ex
    except FileNotFoundError as ex:
        _forensic_finish(forensic_root,status="executor_failed",duration_ms=round((time.perf_counter()-t0)*1000,3),
                         error="Codex execution unavailable")
        raise RuntimeError("Codex execution unavailable/timeout") from ex
    event_count,mcp_count=_forensic_capture_process(
        forensic_root,stdout=run.stdout,stderr=run.stderr,returncode=run.returncode,
        duration_ms=round((time.perf_counter()-t0)*1000,3))
    if run.returncode:
        _forensic_finish(forensic_root,status="process_failed",returncode=run.returncode,
                         duration_ms=round((time.perf_counter()-t0)*1000,3),
                         error=f"Codex failed with exit code {run.returncode}")
        raise CodexCaptureError(f"Codex failed with exit code {run.returncode}; no certification",
                                evidence={"run_id":run_id,"pair_id":pair_id,"forensic_path":str(forensic_root),
                                          "event_count":event_count,"mcp_event_count":mcp_count})
    try:parsed=parse_codex_jsonl(run.stdout)
    except (ValueError,TypeError) as exc:
        _forensic_finish(forensic_root,status="provider_usage_failed",returncode=run.returncode,
                         duration_ms=round((time.perf_counter()-t0)*1000,3),error=str(exc))
        raise CodexCaptureError("Codex JSONL/provider usage evidence unavailable",
                                evidence={"run_id":run_id,"pair_id":pair_id,"forensic_path":str(forensic_root)}) from exc
    if not parsed["mcp_tools"]:
        _forensic_finish(forensic_root,status="route_evidence_failed",returncode=run.returncode,
                         duration_ms=round((time.perf_counter()-t0)*1000,3),
                         error="MCP route evidence unavailable; no mcp_tool_call records")
        raise RuntimeError("MCP route evidence unavailable; no mcp_tool_call records")
    if expected_server is not None and any(
        item.get("server")!=expected_server or item.get("status")!="completed"
        for item in parsed["mcp_tools"]):
        observed=";".join("/".join(str(item.get(k,"")) for k in ("server","tool","status"))
                          for item in parsed["mcp_tools"])
        _forensic_finish(forensic_root,status="route_evidence_failed",returncode=run.returncode,
                         duration_ms=round((time.perf_counter()-t0)*1000,3),
                         error=f"MCP route evidence failed; expected {expected_server}; observed {observed}")
        raise CodexCaptureError(
            f"MCP route evidence failed; expected {expected_server}; observed {observed}",
            evidence={"run_id":run_id,"pair_id":pair_id,"condition":condition,
                      "scenario_id":scenario["scenario_id"],"model":scenario["model"],
                      "expected_mcp_server":expected_server,"runtime_ms":round((time.perf_counter()-t0)*1000,3),
                      "tool_events":parsed["tool_events"],"mcp_tools":parsed["mcp_tools"],
                      "usage":parsed["usage"],"provider_reported":True,
                      "certification_status":"INVALID_ROUTE_EVIDENCE",
                      "forensic_path":str(forensic_root)})
    expected_tools=_expected_mcp_tools(scenario,condition)
    if expected_tools is not None:
        observed_tools=[item.get("tool") for item in parsed["mcp_tools"]]
        if not _observed_mcp_tools_match(scenario,condition,observed_tools):
            _forensic_finish(forensic_root,status="tool_allowlist_failed",returncode=run.returncode,
                             duration_ms=round((time.perf_counter()-t0)*1000,3),
                             error=f"MCP tool allowlist failed; expected {expected_tools} (recovery optional for Web); observed {observed_tools}")
            raise CodexCaptureError(
                f"MCP tool allowlist failed; expected {expected_tools}; observed {observed_tools}",
                evidence={"run_id":run_id,"pair_id":pair_id,"condition":condition,
                          "expected_mcp_server":expected_server,"expected_mcp_tools":expected_tools,
                          "observed_mcp_tools":observed_tools,"forensic_path":str(forensic_root),
                          "certification_status":"INVALID_TOOL_ALLOWLIST"})
    actual=parsed.pop("answer").strip();expected=scenario["expected_exact"].strip()
    oracle_pass,oracle_kind=_evaluate_answer(scenario,actual)
    oracle_diagnostic=_oracle_diagnostic(scenario,actual,oracle_pass)
    _write_json(forensic_root/"oracle-result.json",{
        "status":"evaluated","run_id":run_id,"oracle_kind":oracle_kind,
        "oracle_pass":oracle_pass,"answer_sha256":_sha(actual),
        "expected_sha256":_sha(expected),"diagnostic":oracle_diagnostic})
    _forensic_finish(forensic_root,status="completed" if oracle_pass else "oracle_failed",
                     returncode=run.returncode,duration_ms=round((time.perf_counter()-t0)*1000,3),
                     error=None if oracle_pass else "Oracle mismatch")
    return {"schema":SCHEMA,"condition":condition,"scenario_id":scenario["scenario_id"],
            "repetition":repetition,"run_id":run_id,"pair_id":pair_id,"model":scenario["model"],"codex_version":version,
            "prompt_sha256":_sha(scenario["prompt"]),"expected_sha256":_sha(expected),
            "answer_sha256":_sha(actual),"oracle_kind":oracle_kind,"oracle_pass":oracle_pass,
            "oracle_diagnostic":oracle_diagnostic,
            "workspace_commit":commit,"configuration_sha256":configsha,"profile":effective_profile,
            "runtime_ms":round((time.perf_counter()-t0)*1000,3),
            "tool_events":parsed["tool_events"],"mcp_tools":parsed["mcp_tools"],"usage":parsed["usage"],
            "expected_mcp_server":expected_server,"mcp_route_verified":True,
            "provider_reported":parsed["provider_reported"],"source":parsed["source"],
            "forensic_path":str(forensic_root),
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
    if r.get("condition") not in CONDITIONS or r.get("oracle_kind") not in {"exact_text", "blender_scene_json"} or type(r.get("oracle_pass")) is not bool:
        raise ValueError("Condition/oracle absent")
    for k in ("scenario_id","run_id","pair_id","model","codex_version","prompt_sha256","expected_sha256","workspace_commit","configuration_sha256","expected_mcp_server"):
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
            if a["pair_id"]!=b["pair_id"]:raise ValueError("Mismatched pair_id")
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
