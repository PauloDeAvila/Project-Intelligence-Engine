"""Bounded deterministic Blender scene fingerprints and read-only delta observations.

No bpy import occurs inside the PIE Python interpreter. The snapshot script is
sent to the already configured Blender MCP execute_blender_code tool only when
the user/agent explicitly requests pie_blender_scene_delta. All observations
are local, read-only, scoped and process memory only. No background polling.
"""
from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
import json
from typing import Any

MAX_SNAPSHOT_CHARS = 2_000_000
MAX_ITEMS = 500
MAX_CHANGES = 200
DELTA_SCHEMA = "pie-blender-scene-delta-v1"
MARKER = "PIE_SCENE_SNAPSHOT_V1="

# This code runs inside the Blender addon's Python process through its normal
# execute_blender_code path. No file/network access, blender operators or writes.
# Scope is an allowlisted literal, not executable model-controlled Python.
SNAPSHOT_SCRIPT = r'''
import bpy
import json
import math

def pie_sanitize(value):
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        return round(value, 9) if math.isfinite(value) else str(value)
    try:
        return [pie_sanitize(x) for x in list(value)[:16]]
    except (TypeError, ValueError, OverflowError):
        return str(value)[:100]

def pie_node(node):
    sockets = {}
    for sock in node.inputs:
        if hasattr(sock, "default_value") and not sock.is_linked:
            sockets[sock.identifier or sock.name] = pie_sanitize(sock.default_value)
    props = {}
    for key in ("operation", "blend_type", "vector_type", "noise_dimensions",
                "interpolation", "projection", "extension", "attribute_name",
                "uv_map", "data_type", "clamp", "use_clamp"):
        try:
            value = getattr(node, key)
            if isinstance(value, (str, bool, int, float)):
                props[key] = pie_sanitize(value)
        except (AttributeError, ValueError, TypeError):
            pass
    if hasattr(node, "color_ramp"):
        ramp = node.color_ramp
        props["color_ramp"] = {
            "color_mode": ramp.color_mode, "interpolation": ramp.interpolation,
            "elements": [{"position": pie_sanitize(e.position),
                          "color": pie_sanitize(e.color)} for e in ramp.elements][:64],
            "element_count": len(ramp.elements)}
    if hasattr(node, "image") and node.image is not None:
        props["image"] = {"name": node.image.name, "source": node.image.source}
    return {"name": node.name, "type": node.bl_idname, "inputs": sockets,
            "props": props, "mute": bool(node.mute)}

def pie_material(mat):
    nodes = []
    links = []
    if mat.use_nodes and mat.node_tree:
        nodes = [pie_node(n) for n in sorted(mat.node_tree.nodes, key=lambda n: n.name)[:300]]
        links = [{"from": l.from_node.name, "from_socket": l.from_socket.identifier or l.from_socket.name,
                  "to": l.to_node.name, "to_socket": l.to_socket.identifier or l.to_socket.name}
                 for l in mat.node_tree.links][:1200]
        links.sort(key=lambda x: (x["from"], x["from_socket"], x["to"], x["to_socket"]))
    return {"name": mat.name, "use_nodes": bool(mat.use_nodes),
            "diffuse_color": pie_sanitize(mat.diffuse_color),
            "metallic": pie_sanitize(mat.metallic),
            "roughness": pie_sanitize(mat.roughness),
            "nodes": nodes, "links": links,
            "node_count": len(mat.node_tree.nodes) if mat.use_nodes and mat.node_tree else 0,
            "link_count": len(mat.node_tree.links) if mat.use_nodes and mat.node_tree else 0}

def pie_object(obj):
    return {"name": obj.name, "type": obj.type,
            "location": pie_sanitize(obj.location),
            "rotation_euler": pie_sanitize(obj.rotation_euler),
            "scale": pie_sanitize(obj.scale),
            "visible": not bool(obj.hide_get()),
            "materials": [m.name if m else None for m in (obj.data.materials if
                           obj.type == "MESH" and obj.data is not None else [])][:64],
            "material_slot_count": len(obj.data.materials) if obj.type == "MESH" and obj.data is not None else 0}

pie_scope = __PIE_SCOPE__
pie_scene = bpy.context.scene
pie_objects = sorted(list(bpy.context.selected_objects) if pie_scope == "selected"
                     else list(pie_scene.objects), key=lambda x: x.name)
pie_selected_names = [obj.name for obj in pie_objects]
if pie_scope == "selected":
    pie_materials = {m for obj in pie_objects if obj.type == "MESH" and obj.data is not None
                     for m in obj.data.materials if m is not None}
else:
    pie_materials = set(bpy.data.materials)
pie_materials = sorted(pie_materials, key=lambda m: m.name)
pie_data = {
    "schema": "pie-blender-scene-snapshot-v1",
    "scene": pie_scene.name,
    "scope": pie_scope,
    "objects": [pie_object(o) for o in pie_objects[:500]],
    "materials": [pie_material(m) for m in pie_materials[:200]],
    "omissions": {"objects": max(0, len(pie_objects) - 500),
                  "materials": max(0, len(pie_materials) - 200)},
}
pie_data["complete"] = not any(pie_data["omissions"].values()) and all(
    m["node_count"] == len(m["nodes"]) and m["link_count"] == len(m["links"])
    and all(n["props"].get("color_ramp", {}).get("element_count", 0)
            <= len(n["props"].get("color_ramp", {}).get("elements", []))
            for n in m["nodes"])
    for m in pie_data["materials"]) and all(
    o["material_slot_count"] == len(o["materials"]) for o in pie_data["objects"])
pie_encoded = json.dumps(pie_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
if len(pie_encoded) > 1800000:
    print("PIE_SCENE_SNAPSHOT_V1=" + json.dumps({
        "schema":"pie-blender-scene-snapshot-v1", "scene":pie_scene.name,
        "scope":pie_scope, "complete":False, "omissions":{"payload_too_large":True},
        "objects":[], "materials":[]}, separators=(",", ":")))
else:
    print("PIE_SCENE_SNAPSHOT_V1=" + pie_encoded)
'''


def snapshot_code(scope: str = "selected") -> str:
    if scope not in ("selected", "all"):
        raise ValueError("scope must be selected or all")
    return SNAPSHOT_SCRIPT.replace("__PIE_SCOPE__", repr(scope))


def parse_execution_reply(message: dict[str, Any]) -> dict[str, Any]:
    result = message.get("result")
    if not isinstance(result, dict) or result.get("isError"):
        raise ValueError("Blender MCP execution failed")
    parts = result.get("content")
    if not isinstance(parts, list) or not parts:
        raise ValueError("Blender returned no MCP content")
    text = next((part.get("text", "") for part in parts if
                 isinstance(part, dict) and part.get("type") == "text"), "")
    if not isinstance(text, str) or "Error executing code:" in text or "Rejected by safe mode" in text:
        raise ValueError("Blender execution rejected or failed")
    where = text.find(MARKER)
    if where == -1:
        raise ValueError("Blender did not return the expected read-only snapshot marker")
    payload = text[where + len(MARKER):]
    value, _ = json.JSONDecoder().raw_decode(payload)
    if not isinstance(value, dict) or value.get("schema") != "pie-blender-scene-snapshot-v1":
        raise ValueError("Unsupported Blender snapshot schema")
    return value


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf8")).hexdigest()


def _entity_map(items: Any, kind: str) -> dict[str, dict]:
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise ValueError(f"Invalid {kind} inventory")
    output: dict[str, dict] = {}
    for value in items:
        if not isinstance(value, dict):
            raise ValueError(f"Invalid {kind} element")
        name = value.get("name")
        if not isinstance(name, str) or not name or len(name) > 512 or name in output:
            raise ValueError(f"Invalid or duplicated {kind} name")
        output[name] = value
    return output


def _field_delta(previous: dict, current: dict, max_fields: int = 16) -> dict[str, Any]:
    # Only report concise top-level changes; avoid resending entire node trees.
    fields = {}
    for key in sorted(set(previous) | set(current)):
        if previous.get(key) == current.get(key):
            continue
        if key == "nodes":
            left = _entity_map(previous.get("nodes", []), "nodes")
            right = _entity_map(current.get("nodes", []), "nodes")
            fields[key] = _diff_entities(left, right)
        elif key == "inputs":
            before = previous.get(key, {})
            after = current.get(key, {})
            if isinstance(before, dict) and isinstance(after, dict):
                modified = {
                    name: {"before": before.get(name), "after": after.get(name)}
                    for name in sorted(set(before) | set(after))
                    if before.get(name) != after.get(name)
                }
                fields[key] = {"changed": {name: modified[name] for name in list(modified)[:32]},
                               "omitted": max(0, len(modified) - 32)}
            else:
                fields[key] = {"old_digest": _digest(before), "new_digest": _digest(after)}
        elif key == "links":
            fields[key] = {"old_digest": _digest(previous.get(key)),
                           "new_digest": _digest(current.get(key))}
        else:
            fields[key] = {"before": previous.get(key), "after": current.get(key)}
        if len(fields) >= max_fields:
            fields["additional_changes_omitted"] = True
            break
    return fields


def _diff_entities(old: dict, new: dict) -> dict[str, Any]:
    removed = sorted(set(old) - set(new))
    added = sorted(set(new) - set(old))
    changed = [
        {"name": key, "details": _field_delta(old[key], new[key])}
        for key in sorted(set(old) & set(new)) if _digest(old[key]) != _digest(new[key])
    ]
    counts = {"added": len(added), "removed": len(removed), "changed": len(changed)}
    return {"counts": counts, "added": added[:MAX_CHANGES],
            "removed": removed[:MAX_CHANGES], "changed": changed[:MAX_CHANGES],
            "items_omitted": sum(max(0, len(items) - MAX_CHANGES)
                                 for items in (added, removed, changed))}


class SceneDeltaCache:
    """Stateful, per-scene and per-scope fingerprints; no local disk writes."""

    def __init__(self, capacity: int = 6) -> None:
        self.capacity = capacity
        self._snapshots: OrderedDict[tuple[str, str], tuple[str, dict]] = OrderedDict()

    def observe(self, snapshot: dict, *, max_chars: int = 4000) -> dict[str, Any]:
        if type(max_chars) is not int or not 1000 <= max_chars <= 64000:
            raise ValueError("max_chars must be in 1000..64000")
        if not isinstance(snapshot, dict) or snapshot.get("schema") != "pie-blender-scene-snapshot-v1":
            raise ValueError("Invalid snapshot schema")
        scene, scope = snapshot.get("scene"), snapshot.get("scope")
        if not isinstance(scene, str) or not scene or len(scene) > 512 or scope not in ("selected", "all"):
            raise ValueError("Invalid scene or scope")
        if len(json.dumps(snapshot, ensure_ascii=False)) > MAX_SNAPSHOT_CHARS:
            raise ValueError("Snapshot too large")
        objects = _entity_map(snapshot.get("objects"), "objects")
        materials = _entity_map(snapshot.get("materials"), "materials")
        omissions = snapshot.get("omissions", {})
        if not isinstance(omissions, dict):
            raise ValueError("Invalid omission metadata")
        complete = snapshot.get("complete") is True and not any(omissions.values())
        # A partial snapshot must never replace a complete baseline.
        fingerprint = _digest(snapshot)
        key = (scene, scope)
        previous = self._snapshots.get(key)
        if not complete:
            return {"schema": DELTA_SCHEMA, "state": "PARTIAL", "scene": scene, "scope": scope,
                    "complete": False, "omissions": omissions, "digest": fingerprint,
                    "note": "Partial Blender inventory cannot prove absence or unchanged entities"}
        if previous is None:
            state = "INITIAL"
        elif previous[0] == fingerprint:
            state = "UNCHANGED"
        else:
            state = "DELTA"
        result: dict[str, Any] = {
            "schema": DELTA_SCHEMA, "state": state, "scene": scene, "scope": scope,
            "complete": True, "digest": fingerprint,
            "previous_digest": previous[0] if previous else None,
            "counts": {"objects": len(objects), "materials": len(materials)},
            "coverage": "tracked_object_material_shader_node_fields_only",
        }
        if state == "DELTA":
            old = previous[1]
            result["objects"] = _diff_entities(_entity_map(old["objects"], "objects"), objects)
            result["materials"] = _diff_entities(_entity_map(old["materials"], "materials"), materials)
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > max_chars:
            # Do not update baseline when changes cannot be conveyed faithfully.
            return {"schema": DELTA_SCHEMA, "state": "BUDGET_EXCEEDED",
                    "scene": scene, "scope": scope, "digest": fingerprint,
                    "required_chars": len(encoded), "max_chars": max_chars,
                    "note": "Request a larger budget; current baseline was not changed"}
        self._snapshots[key] = (fingerprint, snapshot)
        self._snapshots.move_to_end(key)
        while len(self._snapshots) > self.capacity:
            self._snapshots.popitem(last=False)
        return result
