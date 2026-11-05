"""Offline, source-aware benchmark token accounting inspired by Ponytail.

Never confuse text estimates, provider usage, cached-inclusive totals or cost.
No inference calls, no networking, no source modification.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path
from statistics import median

from pie.telemetry.tokens import usage as normalize_usage


def _count(value, name):
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError(name + " must be a nonnegative integer or null")
    return value


def _money(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("cost must be numeric or null")
    try:
        amount = Decimal(str(value))
    except Exception as exc:
        raise ValueError("invalid cost") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("cost must be finite and nonnegative")
    return amount


def canonical_usage(payload, provider="openai"):
    """Canonicalize counts, including distinct cache semantics across providers.

    OpenAI cached tokens are INCLUDED in input_tokens. Anthropic cache tokens
    are ADDITIONAL to input_tokens. Missing pieces remain unknown.
    """
    u = normalize_usage(payload, provider)
    inp = _count(u["input_tokens"], "input_tokens")
    out = _count(u["output_tokens"], "output_tokens")
    read = _count(u["cached_input_tokens"], "cached_input_tokens")
    write = _count(u["cache_creation_tokens"], "cache_creation_tokens")
    reasoning = _count(u["reasoning_tokens"], "reasoning_tokens")
    if provider == "openai":
        if read is not None and inp is not None and read > inp:
            raise ValueError("cached tokens exceed total input")
        uncached = inp - read if inp is not None and read is not None else None
        # API total is input+output. Do not add cache read or reasoning twice.
        total = inp + out if inp is not None and out is not None else None
        included = "cache_read_in_input"
    elif provider == "anthropic":
        uncached = inp
        total = inp + out + read + write if all(
            v is not None for v in (inp, out, read, write)
        ) else None
        included = "cache_read_write_additional"
    else:
        raise ValueError("unsupported provider")
    return {
        "provider": provider, "source": "provider_reported",
        "input_tokens": inp, "output_tokens": out,
        "uncached_input_tokens": uncached,
        "cache_read_tokens": read, "cache_write_tokens": write,
        "reasoning_tokens": reasoning,
        "total_tokens": total, "cache_accounting": included,
        "cache_read_share": round(read / inp, 6) if provider == "openai" and inp and read is not None else None,
    }


def _aggregate(rows, provider):
    """Aggregate complete observations only, without converting missing to zero."""
    samples = [canonical_usage(r["usage"], provider) for r in rows]
    keys = ("input_tokens", "output_tokens", "uncached_input_tokens",
            "cache_read_tokens", "cache_write_tokens", "reasoning_tokens", "total_tokens")
    totals = {key: sum(x[key] for x in samples) if samples and all(
        x[key] is not None for x in samples) else None for key in keys}
    return totals, samples


def analyze_cloud_results(document: dict, *, provider="openai", rates=None):
    """Analyze paired PIE cloud benchmark data already saved to disk.

    Allows complete-pair comparisons only and explicitly reports failed calls.
    USD rates (per million tokens) are optional, user-provided and must never
    be mistaken for provider-reported billing.
    """
    if not isinstance(document, dict) or not isinstance(document.get("results"), list):
        raise ValueError("expected benchmark results object")
    model = document.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model required")
    rows = document["results"]
    slots = {}
    for r in rows:
        if not isinstance(r, dict) or type(r.get("repeat")) is not int or not isinstance(r.get("case"), str) or not isinstance(r.get("mode"), str) or type(r.get("ok")) is not bool:
            raise ValueError("malformed result")
        key = (r["repeat"], r["case"], r["mode"])
        if key in slots:
            raise ValueError("duplicate benchmark cell")
        slots[key] = r
    modes = sorted({r["mode"] for r in rows})
    by_mode = {}
    for mode in modes:
        sample = [r for r in rows if r["mode"] == mode]
        valid = [r for r in sample if r["ok"]]
        if any(not isinstance(r.get("usage"), dict) for r in valid):
            raise ValueError("successful row missing usage dictionary")
        totals, parsed = _aggregate(valid, provider)
        latencies = []
        for row in valid:
            sec = row.get("seconds")
            if isinstance(sec, bool) or not isinstance(sec, (float, int)) or sec < 0:
                raise ValueError("invalid latency")
            latencies.append(sec)
        certified = sum(r.get("certification", {}).get("approved") is True for r in valid)
        known = sum(r.get("certification", {}).get("approved") is not None for r in valid)
        by_mode[mode] = {
            "attempted": len(sample), "succeeded": len(valid), "failed": len(sample)-len(valid),
            "median_latency_seconds": median(latencies) if latencies else None,
            "usage": totals,
            "usage_complete": totals["total_tokens"] is not None,
            "certified": certified if known == len(valid) and valid else None,
            "certification_known": known,
            "correct_fields": sum(r.get("semantic_grade", {}).get("passed", 0) for r in valid),
            "graded_fields": sum(r.get("semantic_grade", {}).get("total", 0) for r in valid),
        }
        if rates is not None:
            if set(rates) != {"input_per_million", "output_per_million", "cache_read_per_million", "cache_write_per_million"}:
                raise ValueError("explicit full pricing table required")
            price = {k:_money(v) for k,v in rates.items()}
            if any(v is None for v in price.values()):
                raise ValueError("missing pricing rate")
            costs = []
            for token in parsed:
                if token["uncached_input_tokens"] is None or token["output_tokens"] is None:
                    costs = []; break
                if provider == "openai":
                    if token["cache_read_tokens"] is None:
                        costs = []; break
                    value = (Decimal(token["uncached_input_tokens"]) * price["input_per_million"]
                             + Decimal(token["cache_read_tokens"]) * price["cache_read_per_million"]
                             + Decimal(token["output_tokens"]) * price["output_per_million"]) / 1000000
                else:
                    if token["cache_read_tokens"] is None or token["cache_write_tokens"] is None:
                        costs = []; break
                    value = (Decimal(token["uncached_input_tokens"]) * price["input_per_million"]
                             + Decimal(token["cache_read_tokens"]) * price["cache_read_per_million"]
                             + Decimal(token["cache_write_tokens"]) * price["cache_write_per_million"]
                             + Decimal(token["output_tokens"]) * price["output_per_million"]) / 1000000
                costs.append(value)
            by_mode[mode]["estimated_cost_usd"] = str(sum(costs)) if len(costs) == len(parsed) and costs else None
            by_mode[mode]["cost_source"] = "explicit_rates_estimated_not_billed"
            by_mode[mode]["estimated_cost_per_certified_answer_usd"] = (
                str(sum(costs) / certified) if len(costs) == len(parsed) and costs and certified > 0 and known == len(valid)
                else None
            )
    # Pair on (repeat,case) only; never compare mismatched successes.
    paired = []
    if "baseline" in by_mode and "pie_rtk" in by_mode:
        a = {(r["repeat"],r["case"]):r for r in rows if r["mode"] == "baseline"}
        b = {(r["repeat"],r["case"]):r for r in rows if r["mode"] == "pie_rtk"}
        for key in sorted(set(a) & set(b)):
            left, right = a[key], b[key]
            if not left["ok"] or not right["ok"]:
                continue
            first = canonical_usage(left["usage"],provider)["total_tokens"]
            second = canonical_usage(right["usage"],provider)["total_tokens"]
            paired.append({
                "repeat":key[0],"case":key[1],
                "baseline_tokens":first,"pie_tokens":second,
                "saved_tokens":first-second if first is not None and second is not None else None,
                "latency_delta_seconds":round(right["seconds"]-left["seconds"],6),
            })
    savings = [x["saved_tokens"] for x in paired]
    complete = bool(paired) and all(x is not None for x in savings)
    baseline_total=sum(x["baseline_tokens"] for x in paired) if complete else None
    return {
        "schema":"pie_metrics_v1", "model":model, "provider":provider,
        "measurements":"provider_usage_not_text_estimate",
        "modes":by_mode, "paired_count":len(paired),
        "paired":paired,
        "paired_saved_tokens":sum(savings) if complete else None,
        "paired_reduction_percent":round(100*sum(savings)/baseline_total,3)
        if complete and baseline_total else None,
        "caveat":"Cost uses explicitly supplied rates only. Paired measurements require successful matching runs; no certification implied.",
    }


def analyze_file(source: Path, dest: Path, provider="openai", rates=None):
    result = analyze_cloud_results(json.loads(source.read_text(encoding="utf-8")), provider=provider,rates=rates)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result
