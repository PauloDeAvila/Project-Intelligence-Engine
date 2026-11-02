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
           if x["name"] in names or any(d["path"]==x["path"] and x["line"]<=d["start_line"]<=x["end"] for d in direct)}
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
    tests=[]
    for x in functions:
        if not x["test"]:continue
        hits=x["calls"] & relevant
        naming=sum(1 for n in relevant if n.lower() in x["source"].lower())
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
