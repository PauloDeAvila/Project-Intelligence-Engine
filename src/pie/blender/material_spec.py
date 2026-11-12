"""Deterministic, Blender-independent material job contract.

Only fixed Principled BSDF parameters are accepted. No model-provided code is run.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

_ALLOWED = {"base_color", "metallic", "roughness"}
_NAME = re.compile(r"^[A-Za-z0-9 _.-]{1,80}$")


def normalize_spec(spec: dict) -> dict:
    if not isinstance(spec, dict) or set(spec) != {"version", "materials"}:
        raise ValueError("expected version and materials")
    if spec["version"] != 1:
        raise ValueError("unsupported material specification version")
    materials = spec["materials"]
    if not isinstance(materials, list) or not 1 <= len(materials) <= 100:
        raise ValueError("materials must be a list with 1..100 entries")
    normalized = []
    seen = set()
    for item in materials:
        if not isinstance(item, dict) or not {"name", "base_color", "metallic", "roughness"} == set(item):
            raise ValueError("invalid material keys")
        name = item["name"]
        if not isinstance(name, str) or not _NAME.fullmatch(name) or name in seen:
            raise ValueError("invalid or duplicate material name")
        seen.add(name)
        color = item["base_color"]
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("base_color must be #RRGGBB")
        values = {}
        for key in ("metallic", "roughness"):
            value = item[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be numeric")
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{key} must be finite and in [0,1]")
            values[key] = float(value)
        normalized.append({"name": name, "base_color": color.lower(), **values})
    return {"version": 1, "materials": normalized}


def fingerprint(spec: dict) -> str:
    canonical = json.dumps(normalize_spec(spec), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_spec(path: str | Path) -> dict:
    return normalize_spec(json.loads(Path(path).read_text(encoding="utf-8")))
