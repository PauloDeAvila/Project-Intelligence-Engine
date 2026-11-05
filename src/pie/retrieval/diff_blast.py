"""Git diff to symbol blast radius, using verified PIE graph."""
import json
import re
import subprocess
from pathlib import Path
from pie.graph.verified import VerifiedGraph
from pie.graph.relationships import _drifted_sources
from pie.storage.database import connect

HUNK=re.compile(r"^@@ -[0-9]+(?:,[0-9]+)? \+([0-9]+)(?:,([0-9]+))? @@")

def parse_hunks(diff):
    changed={}; path=None
    for line in diff.splitlines():
        if line.startswith("diff --git "): path=None
        elif line.startswith("+++ b/"):
            path=line[6:]
            if path.startswith("/") or ".." in Path(path).parts: raise ValueError("unsafe diff path")
        elif line.startswith("+++ /dev/null"): path=None
        elif path:
            m=HUNK.match(line)
            if m:
                a=int(m.group(1)); length=int(m.group(2) or "1")
                changed.setdefault(path,[]).append((max(1,a),max(1,a+max(1,length)-1)))
    return changed

def blast_diff(root, *, depth=2, limit=50, max_chars=16000):
    if type(depth) is not int or not 0<=depth<=5: raise ValueError("invalid depth")
    if type(limit) is not int or not 1<=limit<=100: raise ValueError("invalid limit")
    if type(max_chars) is not int or not 1000<=max_chars<=64000: raise ValueError("invalid budget")
    root=Path(root).resolve(strict=True)
    def git(*args):
        run=subprocess.run(["git","-C",str(root),*args],capture_output=True,
                           text=True,timeout=15,check=False)
        if run.returncode: raise ValueError("git failed")
        return run.stdout
    if Path(git("rev-parse","--show-toplevel").strip()).resolve(strict=True)!=root:
        raise ValueError("root must be git worktree root")
    raw=git("diff","HEAD","--no-ext-diff","--no-renames","--unified=0","--",".")
    if len(raw)>1000000: raise ValueError("diff too large")
    changes=parse_hunks(raw)
    with connect(root/".pie"/"index.sqlite3") as db:
        state=db.execute("SELECT value FROM metadata WHERE key='index_state'").fetchone()
        if not state or state[0]!="CURRENT": raise ValueError("index not current")
        if _drifted_sources(db,root): raise ValueError("index stale; run pie index")
        graph=VerifiedGraph.from_connection(db)
        seeds=[]
        for path,ranges in sorted(changes.items()):
            rows=db.execute("SELECT qualified_name,start_line,end_line FROM symbols s JOIN files f ON f.id=s.file_id WHERE f.path=? ORDER BY end_line-start_line,start_line,qualified_name",(path,)).fetchall()
            for first,last in ranges:
                hits=[r for r in rows if r["start_line"]<=last and r["end_line"]>=first]
                if hits:
                    size=min(r["end_line"]-r["start_line"] for r in hits)
                    for r in hits:
                        if r["end_line"]-r["start_line"]==size:
                            item={"path":path,"symbol":r["qualified_name"],"lines":[first,last]}
                            if item not in seeds: seeds.append(item)
    impacts=[]; incomplete=False
    for seed in seeds:
        trace=graph.consumers(seed["path"],seed["symbol"],depth=depth,limit=500)
        incomplete|=trace["truncated"]
        for edge in trace["edges"]:
            item={"from":seed["symbol"],"consumer_path":edge["source_path"],
                  "consumer":edge["consumer"],"line":edge["source_line"],
                  "depth":edge["depth"],"resolution":"verified",
                  "impact":"potential_not_runtime_proof"}
            if item not in impacts: impacts.append(item)
    impacts.sort(key=lambda x:(x["depth"],x["consumer_path"],x["line"],x["from"]))
    result={"state":"CURRENT","method":"git_diff_verified_blast_v1",
            "changed_files":sorted(changes),"seeds":seeds,
            "potential_consumers":impacts[:limit],
            "omitted":max(0,len(impacts)-limit),
            "traversal_incomplete":incomplete,"untracked_files_included":False,
            "note":"Verified static bindings do not establish runtime effects or exhaustive dependencies."}
    size=lambda:len(json.dumps(result,ensure_ascii=False,separators=(",",":")))
    while size()>max_chars and result["potential_consumers"]:
        result["potential_consumers"].pop();result["omitted"]+=1;result["state"]="PARTIAL"
    if size()>max_chars: raise ValueError("metadata exceeds budget")
    return result
