"""Deterministic verified-edge PageRank retrieval, adapted from Trail-Code principles."""
import math
import json
from pathlib import Path
from pie.retrieval.intelligence import smart_context
from pie.graph.verified import VerifiedGraph
from pie.graph.relationships import _drifted_sources
from pie.storage.database import connect

def pagerank(nodes, edges, seeds, alpha=0.25, iterations=20):
    nodes=sorted(set(nodes))
    if not nodes: return {}
    if len(nodes)>1000 or not 0<alpha<=1 or not 1<=iterations<=50: raise ValueError("invalid graph")
    restart={n:float(seeds.get(n,0)) for n in nodes}
    if not all(math.isfinite(x) for x in restart.values()): raise ValueError("nonfinite seeds")
    restart={n:max(0.0,x) for n,x in restart.items()}
    total=sum(restart.values())
    if not total: return {n:0.0 for n in nodes}
    restart={n:x/total for n,x in restart.items()}
    adj={n:set() for n in nodes}
    for a,b in edges:
        if a in adj and b in adj and a!=b: adj[a].add(b); adj[b].add(a)
    score=dict(restart)
    for _ in range(iterations):
        next_score={n:alpha*restart[n] for n in nodes}
        dangling=0.0
        for n in nodes:
            if not adj[n]: dangling+=score[n]
            else:
                for b in adj[n]: next_score[b]+=(1-alpha)*score[n]/len(adj[n])
        for n in nodes: next_score[n]+=(1-alpha)*dangling*restart[n]
        score=next_score
    return score

def rank_context(root, query, *, limit=5, max_chars=12000, candidates=40):
    if not isinstance(query,str) or not query.strip() or len(query)>1024: raise ValueError("bad query")
    if type(limit) is not int or not 1<=limit<=20: raise ValueError("bad limit")
    if type(max_chars) is not int or not 1000<=max_chars<=64000: raise ValueError("bad budget")
    if type(candidates) is not int or not limit<=candidates<=100: raise ValueError("bad candidate count")
    root=Path(root).resolve(strict=True)
    base=smart_context(root,query,limit=candidates,max_chars=200000,include_body=False)
    if base["context_state"]!="CURRENT" or base["diagnostics"]: raise ValueError("stale context")
    with connect(root/".pie"/"index.sqlite3") as db:
        if _drifted_sources(db,root): raise ValueError("stale graph")
        graph=VerifiedGraph.from_connection(db)
    evidence=base["evidence"]
    names={(e["path"],e["symbol"]) for e in evidence}
    seed={(e["path"],e["symbol"]):e["score"] for e in evidence}
    links=set()
    for a in names:
        for e in graph.forward.get(a,()):
            b=(e.target_path,e.target_symbol)
            if b in names and a!=b: links.add(tuple(sorted((a,b))))
    weights=pagerank(names,links,seed)
    scale=max(weights.values(),default=0)
    ranked=[]
    for e in evidence:
        factor=weights.get((e["path"],e["symbol"]),0)/scale if scale else 0
        ranked.append({**e,"graph_score":round(factor,6),"rank_score":round(e["score"]+5*factor,6)})
    ranked.sort(key=lambda e:(-e["rank_score"],-e["score"],e["path"],e["start_line"],e["symbol"]))
    result={"query":query,"method":"verified_ppr_v1","context_state":"CURRENT",
            "edges":len(links),"candidate_count":len(ranked),"candidate_pool_omitted":base["omitted"],
            "evidence":ranked[:limit],"omitted":max(0,len(ranked)-limit)+base["omitted"],
            "note":"Graph score is a heuristic; only bound edges are verified."}
    size=lambda:len(json.dumps(result,ensure_ascii=False,separators=(",",":")))
    while size()>max_chars and result["evidence"]:
        result["evidence"].pop();result["omitted"]+=1;result["context_state"]="PARTIAL"
    if size()>max_chars: raise ValueError("metadata exceeds budget")
    return result
