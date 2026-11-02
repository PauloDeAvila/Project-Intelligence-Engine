"""Cloud-side diagnostic for an OpenAI-compatible 9Router gateway.

Deliberately never prints/stores authentication headers or the gateway URL.
The report contains only sanitized status, duration, and model identifiers.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

out = Path("gateway-check.json")
model = os.environ.get("TARGET_MODEL", "").strip()
base = os.environ.get("PIE_API_BASE_URL", "").rstrip("/")
key = os.environ.get("PIE_API_KEY", "")
report = {"model_requested": model, "reachable": False, "http_status": None, "elapsed_seconds": None, "actual_model": None, "error_category": None, "configuration": {"model_present": bool(model), "base_url_present": bool(base), "base_url_https": base.startswith("https://"), "api_key_present": bool(key)}}

if not model or not base.startswith("https://") or not key:
    report["error_category"] = "invalid_configuration"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    sys.exit("Invalid gateway configuration")

payload = {"model": model, "messages": [{"role": "user", "content": "Responda apenas OK."}], "max_tokens": 64, "stream": False}
request = urllib.request.Request(
    base + "/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
)
start = time.monotonic()
try:
    with urllib.request.urlopen(request, timeout=45) as response:
        data = json.load(response)
        report["http_status"] = response.status
        report["actual_model"] = data.get("model")
        report["reachable"] = bool(data.get("choices"))
        if not report["reachable"]:
            report["error_category"] = "empty_completion"
except urllib.error.HTTPError as error:
    report["http_status"] = error.code
    report["error_category"] = "gateway_http_error"
except (urllib.error.URLError, TimeoutError, OSError):
    report["error_category"] = "network_or_timeout"
finally:
    report["elapsed_seconds"] = round(time.monotonic() - start, 3)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

print("Gateway check:", json.dumps(report, ensure_ascii=False))
if not report["reachable"]:
    sys.exit(1)
