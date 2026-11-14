"""Model-aware text estimates and normalized provider-reported token usage."""
from __future__ import annotations
import json
import math

def estimate(text: str, model: str = "unknown") -> dict:
    if not isinstance(text,str): raise TypeError("text must be str")
    if not isinstance(model,str) or not model.strip(): raise ValueError("model required")
    try:
        import tiktoken
        enc=tiktoken.encoding_for_model(model)
    except (ImportError,KeyError):
        tokens=math.ceil(len(text.encode("utf-8"))/4)
        method,tokenizer="heuristic","utf8_bytes_div_4"
    else:
        tokens=len(enc.encode(text,disallowed_special=()))
        method,tokenizer="tokenizer_estimate",enc.name
    return {"tokens":tokens,"model":model,"method":method,"tokenizer":tokenizer,
            "scope":"text_only","provider_reported":False}

def compare(original: str, optimized: str, model: str = "unknown") -> dict:
    a,b=estimate(original,model),estimate(optimized,model)
    saved=a["tokens"]-b["tokens"]
    return {"original":a,"optimized":b,"saved_tokens":saved,
            "reduction_percent":round(saved/a["tokens"]*100,3) if a["tokens"] else (0 if not b["tokens"] else None),
            "quality_verified":False}

def _nonnegative(value,field):
    if value is None: return None
    if type(value) is not int or value<0: raise ValueError(f"{field} must be nonnegative integer")
    return value

def usage(payload: dict, provider: str) -> dict:
    """Read API counters without claiming text estimates are billing measurements."""
    if not isinstance(payload,dict): raise TypeError("payload must be dict")
    data=payload.get("usage",payload)
    if not isinstance(data,dict): raise ValueError("usage must be dict")
    if provider=="openai":
        inside=data.get("prompt_tokens_details") or data.get("input_tokens_details") or {}
        outside=data.get("completion_tokens_details") or data.get("output_tokens_details") or {}
        if not isinstance(inside,dict) or not isinstance(outside,dict): raise ValueError("invalid token details")
        raw=(data.get("prompt_tokens",data.get("input_tokens")),
             data.get("completion_tokens",data.get("output_tokens")),
             inside.get("cached_tokens"),None,outside.get("reasoning_tokens"))
    elif provider=="anthropic":
        raw=(data.get("input_tokens"),data.get("output_tokens"),
             data.get("cache_read_input_tokens"),data.get("cache_creation_input_tokens"),None)
    else: raise ValueError("unsupported provider")
    keys=("input_tokens","output_tokens","cached_input_tokens","cache_creation_tokens","reasoning_tokens")
    return {"provider":provider,"method":"provider_reported","scope":"api_usage",
            **{k:_nonnegative(v,k) for k,v in zip(keys,raw)}}

def serialized(value, model: str = "unknown") -> dict:
    return estimate(json.dumps(value,ensure_ascii=False,separators=(",",":")),model)
