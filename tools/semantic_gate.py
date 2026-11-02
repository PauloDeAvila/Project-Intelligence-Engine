import json

def verify_fields(raw_answer, observed):
    try:
        candidate = json.loads(raw_answer)
    except (TypeError, ValueError):
        return {"approved": False, "failed": list(observed)}
    if not isinstance(candidate, dict):
        return {"approved": False, "failed": list(observed)}
    failed = [key for key, expected in observed.items() if key not in candidate or type(candidate[key]) is not type(expected) or candidate[key] != expected]
    if set(candidate) != set(observed):
        failed.append("schema_mismatch")
    return {"approved": not failed, "failed": failed}
