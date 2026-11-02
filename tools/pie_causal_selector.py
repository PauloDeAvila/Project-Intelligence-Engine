"""General AST-based causal evidence selector, without question-specific file lists.

Static relationships are approximate: dynamic dispatch and monkey-patching are not resolved.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
from pie.retrieval.context import build_context
from pie.storage.database import connect


def _functions(tree):
    parents={}
    for p in ast.walk(tree):
        for c in ast.iter_child_nodes(p):parents[c]=p
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            p=parents.get(node)
            cls=p.name if isinstance(p,ast.ClassDef) else None
            yield node, (cls+"." if cls else "")+node.name


def _calls(node):
    result=set()
    for n in ast.walk(node):
        if not isinstance(n,ast.Call):continue
        if isinstance(n.func,ast.Name):result.add(n.func.id)
        elif isinstance(n.func,ast.Attribute):result.add(n.func.attr)
    return result


def build_causal_context(root:Path,query:str,max_chars:int=12000)->dict:
    root=Path(root).resolve()
    raw=build_context(root,query,max_chars=max_chars)
    report={"query":query,"context_state":raw["context_state"],"evidence":[],"omitted":[],
            "notes":"Hash-verified AST evidence; syntactic candidate calls, not guaranteed runtime call edges."}
    if raw["context_state"]!="CURRENT":return report

    with connect(root/".pie"/"index.sqlite3") as db:
        files=db.execute("SELECT path,sha256 FROM files ORDER BY path").fetchall()
    functions=[]
    names={query.rsplit(".",1)[-1]}
    direct=raw.get("source_ranges",[])+raw.get("expanded_source_ranges",[])
    for d in direct:
        if d.get("kind") in ("function","method","constant"):names.add(d["symbol"].rsplit(".",1)[-1])

    for file in files:
        path=file["path"]
        try:
            b=(root/path).read_bytes()
            if hashlib.sha256(b).hexdigest()!=file["sha256"]:raise ValueError("stale")
            lines=b.decode("utf-8-sig").splitlines()
            tree=ast.parse("\n".join(lines),filename=path)
        except (OSError,UnicodeError,SyntaxError,ValueError):
            report["context_state"]="STALE"
            report["omitted"].append({"path":path,"reason":"unavailable_or_stale"})
            return report
        for node,qualified in _functions(tree):
            functions.append({"path":path,"line":node.lineno,"end":node.end_lineno,"name":node.name,
                              "qualified":qualified,"calls":_calls(node),
                              "source":"\n".join(lines[node.lineno-1:node.end_lineno]),
                              "test":path.startswith("tests/") or "/tests/" in path or Path(path).name.startswith("test_")})

    production=[x for x in functions if not x["test"]]
    seeds={x["name"] for x in production
           if x["name"] in names or query.rsplit(".",1)[-1] in x["source"] or any(d["path"]==x["path"] and x["line"]<=d["start_line"]<=x["end"] for d in direct)}
    relevant=set(seeds)
    for _ in range(2):
        relevant |= {x["name"] for x in production if x["calls"] & relevant}

    def relevance(x):
        direct_hit=x["name"] in names
        calls=x["calls"] & relevant
        hit=x["name"] in relevant
        return 100*direct_hit+50*hit+20*len(calls)

    ranked=sorted((x for x in production if relevance(x)>0),key=lambda x:(-relevance(x),len(x["source"]),x["path"]))
    behavior_words={"assertRaises","assertEqual","assert_called_once","assert_called_once_with","raises"}
    owner_types={x["qualified"].split(".",1)[0] for x in ranked if "." in x["qualified"]}
    tests=[]
    for x in functions:
        if not x["test"]:continue
        hits=x["calls"] & relevant
        naming=sum(1 for n in relevant|owner_types if n.lower() in x["source"].lower())
        if not hits and not naming:continue
        score=10*len(hits)+naming+5*bool(x["calls"] & behavior_words)
        if "contract" in x["path"].lower() or "references" in x["source"].lower():score-=100
        if any(word in x["name"].lower() for word in ("rollback","retry","failure","error")):score+=12
        if score>0:tests.append((score,x))
    tests.sort(key=lambda pair:(-pair[0],len(pair[1]["source"])))

    seen=set()
    def add(path,start,end,content,kind,name):
        identity=(path,start,end)
        if identity in seen:return
        evidence={"path":path,"start_line":start,"end_line":end,"symbol":name,"kind":kind,"content":content}
        candidate=dict(report,evidence=report["evidence"]+[evidence])
        if len(json.dumps(candidate,ensure_ascii=False))>max_chars:
            report["omitted"].append({"path":path,"symbol":name,"reason":"budget"})
            return
        report["evidence"].append(evidence)
        seen.add(identity)

    for d in direct:
        if d.get("kind") in ("constant","class") and d["symbol"].rsplit(".",1)[-1]==query.rsplit(".",1)[-1]:
            add(d["path"],d["start_line"],d["end_line"],d["content"],"definition",d["symbol"])
    for x in ranked[:9]:add(x["path"],x["line"],x["end"],x["source"],"function",x["qualified"])
    for _,x in tests[:4]:add(x["path"],x["line"],x["end"],x["source"],"behavioral_test",x["qualified"])
    if report["omitted"]:report["context_state"]="PARTIAL"
    return report

def extract_control_flow(report:dict)->list[str]:
    """AST-derived control-flow annotations, independent of question identity.

    These are syntactic facts, not proofs of runtime dispatch.
    """
    import textwrap
    facts=[]
    seen=set()
    for item in report.get("evidence",[]):
        if item.get("kind")!="function":continue
        src=textwrap.dedent(item.get("content",""))
        try: tree=ast.parse(src)
        except SyntaxError:continue
        functions=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
        if not functions:continue
        fn=functions[0]
        name=item.get("symbol",fn.name)
        path=item.get("path","?")
        for node in ast.walk(fn):
            if not isinstance(node,(ast.Try,ast.TryStar)):continue
            source=f"{path}::{name}"
            for stmt in node.body:
                if isinstance(stmt,ast.Return):
                    value=ast.unparse(stmt.value) if stmt.value else "None"
                    fact=f"{source}: TRY_RETURN {value}; o except só executa se ocorrer uma exceção, não por retorno None"
                    if fact not in seen:facts.append(fact);seen.add(fact)
            for handler in node.handlers:
                exc=ast.unparse(handler.type) if handler.type else "BaseException"
                action=[]
                for stmt in handler.body:
                    for call in ast.walk(stmt):
                        if isinstance(call,ast.Call):action.append(ast.unparse(call.func))
                    if isinstance(stmt,ast.Raise) and stmt.exc is None:
                        action.append("re-raise original exception unless earlier action fails")
                if action:
                    fact=f"{source}: HANDLER {exc} executa {', '.join(dict.fromkeys(action))}"
                    if fact not in seen:facts.append(fact);seen.add(fact)
                for stmt in handler.body:
                    for call in ast.walk(stmt):
                        if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute):
                            fact=f"{source}: ATTRIBUTE_CALL {ast.unparse(call.func)} dentro do handler; ausência do atributo pode gerar AttributeError e substituir a exceção em propagação"
                            if fact not in seen:facts.append(fact);seen.add(fact)
    return facts[:15]


def render_control_flow(report:dict)->str:
    return "\n".join(extract_control_flow(report))
