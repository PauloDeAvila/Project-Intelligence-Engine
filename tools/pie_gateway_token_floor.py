"""Measure the gateway-reported floor of prompt tokens with minimal code-free calls."""
import json
import os
from pathlib import Path
import statistics
import time
import urllib.request

def run():
    base=os.environ["PIE_API_BASE_URL"].rstrip("/")
    key=os.environ["PIE_API_KEY"]
    cases=[
        ("tiny","OK"),
        ("short","Find the word hello in this sentence."),
        ("medium","Describe how a function is located in a Python repository. "*20),
    ]
    rows=[]
    for label,prompt in cases:
        for repeat in range(3):
            payload={"model":"gh/gpt-4o-mini","messages":[
                {"role":"system","content":"Answer succinctly."},
                {"role":"user","content":prompt}],
                "max_tokens":64,"stream":False}
            req=urllib.request.Request(base+"/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Content-Type":"application/json","Authorization":"Bearer "+key})
            begin=time.perf_counter()
            with urllib.request.urlopen(req,timeout=90) as response:data=json.load(response)
            rows.append({"case":label,"repeat":repeat,"visible_chars":len(prompt),
                         "prompt_tokens":data.get("usage",{}).get("prompt_tokens"),
                         "completion_tokens":data.get("usage",{}).get("completion_tokens"),
                         "latency_s":round(time.perf_counter()-begin,3),
                         "actual_model":data.get("model")})
            time.sleep(.2)
    out=Path("gateway-token-floor.json")
    out.write_text(json.dumps(rows,indent=2),encoding="utf-8")
    print("TOKEN_FLOOR",json.dumps({name:{"median_tokens":statistics.median(x["prompt_tokens"] for x in rows if x["case"]==name)} for name,_ in cases}))
if __name__=="__main__":run()
