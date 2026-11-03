"""Source-grounded responsibility packs; deterministic and fail-closed."""
from __future__ import annotations
import json
import time
from hashlib import sha256

def _size(obj):
    return len(json.dumps(obj,ensure_ascii=False,separators=(",",":")))

def build_responsibility_pack(root, question, evidence, graph, conn, *, max_chars=12000, max_edges=12, timings=None):
    if not 500 <= max_chars <= 200000 or not 0 <= max_edges <= 100:
        raise ValueError("Invalid pack limits")
    if evidence.get("context_state") not in ("CURRENT", "PARTIAL"):
        raise ValueError("Cannot create pack from stale or incomplete evidence")
    pack={"query":question,"context_state":evidence["context_state"],"responsibilities":[],
          "omitted":0,"graph_semantics":"verified references, potential impact only"}
    seen=set()
    for candidate in evidence["evidence"]:
        identity=(candidate["path"],candidate["symbol"],candidate["start_line"])
        if identity in seen:
            continue
        seen.add(identity)
        row=conn.execute("SELECT sha256 FROM files WHERE path=?",(candidate["path"],)).fetchone()
        if row is None:
            raise ValueError("Missing indexed source")
        source=(root/candidate["path"]).resolve()
        if not source.is_relative_to(root.resolve()) or (root/candidate["path"]).is_symlink():
            raise ValueError("Escaping source path")
        if sha256(source.read_bytes()).hexdigest()!=row[0]:
            raise ValueError("Source changed during pack creation")
        graph_started = time.perf_counter()
        links=graph.consumers(candidate["path"],candidate["symbol"],depth=2,limit=max(1,max_edges))["edges"] if max_edges else []
        if timings is not None:
            timings["graph_ms"] = timings.get("graph_ms", 0.0) + (time.perf_counter() - graph_started) * 1000
        item={"responsibility":candidate["description"],"path":candidate["path"],
              "symbol":candidate["symbol"],"start_line":candidate["start_line"],
              "end_line":candidate["end_line"],"sha256":row[0],
              "source":candidate.get("content",""),"verified_consumers":links[:max_edges]}
        tentative={**pack,"responsibilities":pack["responsibilities"]+[item]}
        if _size(tentative)<=max_chars:
            pack["responsibilities"].append(item)
            continue
        item["verified_consumers"]=[]
        tentative={**pack,"responsibilities":pack["responsibilities"]+[item]}
        if _size(tentative)<=max_chars:
            pack["responsibilities"].append(item)
        else:
            pack["omitted"]+=1
    pack["serialized_chars"]=_size(pack)
    while _size(pack)>max_chars and pack["responsibilities"]:
        pack["responsibilities"].pop()
        pack["omitted"]+=1
        pack["serialized_chars"]=_size(pack)
    pack["serialized_chars"]=_size(pack)
    return pack
