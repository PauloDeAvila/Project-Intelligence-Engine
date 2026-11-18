"""Bounded deterministic Blender scene fingerprints and read-only delta observations.

No bpy import occurs inside the PIE Python interpreter. The snapshot script is
sent to the already configured Blender MCP execute_blender_code tool only when
the user/agent explicitly requests pie_blender_scene_delta. All observations
are local, read-only and scoped. Engine state lives in process memory unless a persistent delta store root is
configured, in which case only scene fingerprints (digests, counts, timestamps)
are persisted to a table in the existing ``index.sqlite3`` under the workspace
storage directory. No background polling.
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

from pie.storage.locations import workspace_storage

MAX_SNAPSHOT_CHARS = 2_000_000
MAX_ITEMS = 500
MAX_CHANGES = 200
DELTA_SCHEMA = "pie-blender-scene-delta-v1"
QUERY_SCHEMA = "pie-blender-query-scene-v1"
MARKER = "PIE_SCENE_SNAPSHOT_V1="
QUERY_MARKER = "PIE_QUERY_SCENE_V1="
GET_OBJECT_MARKER = "PIE_GET_OBJECT_V1="

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


QUERY_TOOL_NAMES = frozenset({"find_objects"})
QUERY_FIELDS = frozenset({"name", "type", "material_count", "material_names", "location"})


def validate_query_arguments(arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ValueError("Query arguments must be an object")
    allowed = {"query", "filters", "fields", "limit", "offset"}
    if set(arguments) - allowed:
        raise ValueError("Unknown query argument")
    query = arguments.get("query", "find_objects")
    if query not in QUERY_TOOL_NAMES:
        raise ValueError("Unsupported scene query")
    filters = arguments.get("filters", {})
    if not isinstance(filters, dict) or set(filters) - {"name_prefix", "name_contains"}:
        raise ValueError("Invalid scene query filters")
    for key in ("name_prefix", "name_contains"):
        if key in filters and (not isinstance(filters[key], str) or len(filters[key]) > 128):
            raise ValueError("Invalid scene query filter")
    fields = arguments.get("fields", ["name", "type", "material_count"])
    if not isinstance(fields, list) or not fields or len(fields) > 8 or any(
        field not in QUERY_FIELDS for field in fields
    ) or len(set(fields)) != len(fields):
        raise ValueError("Invalid scene query fields")
    limit = arguments.get("limit", 20)
    offset = arguments.get("offset", 0)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if type(offset) is not int or not 0 <= offset <= 10000:
        raise ValueError("offset must be between 0 and 10000")
    return {"query": query, "filters": filters, "fields": fields,
            "limit": limit, "offset": offset}


def query_scene_code(arguments: Any) -> str:
    args = validate_query_arguments(arguments)
    # Only validated JSON literals are embedded; no model-provided Python is executed.
    query = json.dumps(args["query"], ensure_ascii=False)
    filters = json.dumps(args["filters"], ensure_ascii=False, sort_keys=True)
    fields = json.dumps(args["fields"], ensure_ascii=False)
    limit, offset = args["limit"], args["offset"]
    return f'''import bpy, json
pie_query = {query}
pie_filters = {filters}
pie_fields = {fields}
pie_limit = {limit}
pie_offset = {offset}
pie_scene = bpy.context.scene
pie_objects = sorted(list(pie_scene.objects), key=lambda item: item.name)
if pie_query == "find_objects":
    pie_objects = [obj for obj in pie_objects
                   if (not pie_filters.get("name_prefix") or obj.name.startswith(pie_filters["name_prefix"]))
                   and (not pie_filters.get("name_contains") or pie_filters["name_contains"].lower() in obj.name.lower())]
pie_total = len(pie_objects)
pie_page = pie_objects[pie_offset:pie_offset + pie_limit]
pie_items = []
for obj in pie_page:
    pie_item = {{}}
    if "name" in pie_fields: pie_item["name"] = obj.name
    if "type" in pie_fields: pie_item["type"] = obj.type
    if "material_count" in pie_fields:
        pie_item["material_count"] = len(obj.data.materials) if obj.type == "MESH" and obj.data else 0
    if "material_names" in pie_fields:
        pie_item["material_names"] = [m.name for m in obj.data.materials if m] if obj.type == "MESH" and obj.data else []
    if "location" in pie_fields:
        pie_item["location"] = [round(float(value), 6) for value in obj.location]
    pie_items.append(pie_item)
pie_data = {{"schema": "{QUERY_SCHEMA}", "query": pie_query, "scene": pie_scene.name,
            "items": pie_items, "total": pie_total, "offset": pie_offset, "limit": pie_limit,
            "next_offset": pie_offset + pie_limit if pie_offset + pie_limit < pie_total else None,
            "complete": pie_offset + len(pie_page) >= pie_total}}
print("{QUERY_MARKER}" + json.dumps(pie_data, ensure_ascii=False, sort_keys=True, separators=(",", ":")))'''


def validate_get_object_arguments(arguments: Any) -> str:
    """Require one exact name; never accept arbitrary Python or mutating options."""
    if not isinstance(arguments, dict) or set(arguments) != {"name"}:
        raise ValueError("Exact Blender object query needs only name")
    name = arguments["name"]
    if not isinstance(name, str) or not name or len(name) > 128:
        raise ValueError("Invalid exact Blender object name")
    return name


def get_object_code(arguments: Any) -> str:
    """Generate a read-only bpy expression with a JSON-escaped literal name."""
    encoded_name = json.dumps(validate_get_object_arguments(arguments), ensure_ascii=True)
    return f'''import bpy, json
pie_object_name = {encoded_name}
pie_object = bpy.context.scene.objects.get(pie_object_name)
if pie_object is None:
    print("{GET_OBJECT_MARKER}" + json.dumps({{"error":"OBJECT_NOT_FOUND"}}))
else:
    pie_value = {{
        "object_name": pie_object.name,
        "object_type": pie_object.type,
        "location": [round(float(v), 6) for v in pie_object.location],
        "material_names": [m.name for m in pie_object.data.materials if m] if pie_object.type == "MESH" and pie_object.data else []
    }}
    print("{GET_OBJECT_MARKER}" + json.dumps(pie_value, ensure_ascii=False, separators=(",", ":")))'''


def parse_get_object_reply(message: dict[str, Any]) -> dict[str, Any]:
    """Return only the four requested fields; reject malformed or missing objects."""
    result = message.get("result")
    if not isinstance(result, dict) or result.get("isError"):
        raise ValueError("Blender exact object lookup failed")
    candidates = [
        part.get("text") for part in result.get("content", [])
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and isinstance(structured.get("result"), str):
        candidates.append(structured["result"])
    for content in candidates:
        where = content.find(GET_OBJECT_MARKER)
        if where < 0:
            continue
        try:
            value, _ = json.JSONDecoder().raw_decode(content[where + len(GET_OBJECT_MARKER):])
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid Blender exact object JSON") from exc
        if isinstance(value, dict) and value.get("error") == "OBJECT_NOT_FOUND":
            raise ValueError("Blender object not found in current scene")
        required = {"object_name", "object_type", "location", "material_names"}
        if (not isinstance(value, dict) or set(value) != required
                or not isinstance(value["object_name"], str)
                or not isinstance(value["object_type"], str)
                or not isinstance(value["location"], list)
                or len(value["location"]) != 3
                or any(type(v) not in (int, float) for v in value["location"])
                or not isinstance(value["material_names"], list)
                or any(not isinstance(m, str) for m in value["material_names"])):
            raise ValueError("Invalid exact Blender object structure")
        return value
    raise ValueError("Missing exact Blender object marker")


def parse_query_reply(message: dict[str, Any]) -> dict[str, Any]:
    result = message.get("result")
    if not isinstance(result, dict) or result.get("isError"):
        raise ValueError("Blender scene query failed")
    candidates = []
    parts = result.get("content")
    candidates.extend(part.get("text", "") for part in parts or []
                      if isinstance(part, dict) and part.get("type") == "text")
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and isinstance(structured.get("result"), str):
        candidates.append(structured["result"])
    for text in candidates:
        if not isinstance(text, str):
            continue
        where = text.find(QUERY_MARKER)
        if where != -1:
            value, _ = json.JSONDecoder().raw_decode(text[where + len(QUERY_MARKER):])
            break
    else:
        if any("Error executing code:" in text or "Could not connect to Blender" in text
               for text in candidates if isinstance(text, str)):
            raise ValueError("Blender scene query execution failed")
        raise ValueError("Blender did not return the expected scene query marker")
    if not isinstance(value, dict) or value.get("schema") != QUERY_SCHEMA:
        raise ValueError("Unsupported scene query schema")
    return value


DELTA_STORE_SCHEMA = "pie-blender-scene-delta-store-v1"


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


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
    """Stateful, per-scene and per-scope fingerprints.

    Without ``root`` the cache is process memory only (previous behavior).
    With ``root`` fingerprints of the last complete baselines are persisted
    to a table in the existing ``index.sqlite3`` under the workspace storage
    directory, so a new process observing an identical scene reports
    UNCHANGED instead of INITIAL.

    Privacy: only digests, scene/scope names, entity counts and timestamps
    are stored. No snapshot content, no entity fields, no prompts, model
    replies, credentials or cookies are ever written.

    Persistence is best-effort and fail-closed in the privacy sense: a
    persistence error never alters the state returned by ``observe``; it is
    reported via ``persistence_diagnostic`` and persistence is disabled for
    the remainder of the process.
    """

    STORE_VERSION = 1
    _TABLE = "scene_delta_fingerprints"
    _HISTORY_TABLE = "scene_delta_fingerprint_history"
    _HISTORY_LIMIT = 5

    def __init__(self, capacity: int = 6, root: str | os.PathLike[str] | None = None) -> None:
        if type(capacity) is not int or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        # (scene, scope) -> (digest, counts, updated_at); counts is a JSON string.
        self._fingerprints: OrderedDict[tuple[str, str], tuple[str, str, str]] = OrderedDict()
        self._lock = threading.RLock()
        self._persist_error: str | None = None
        self._db_path: Path | None = None
        if root is not None:
            try:
                self._db_path = self._resolve_db(root)
                self._load_store()
            except (OSError, ValueError, sqlite3.Error) as exc:
                self._persist_error = f"{type(exc).__name__}: {exc}"
                self._db_path = None

    # ------------------------------------------------------------------ persistence
    @staticmethod
    def _resolve_db(root: str | os.PathLike[str]) -> Path:
        root_path = Path(root).expanduser().resolve(strict=True)
        if not root_path.is_dir():
            raise ValueError("Project root must be a directory")
        storage_dir = workspace_storage(root_path)
        if storage_dir.is_symlink() or storage_dir.resolve() != workspace_storage(root_path).resolve():
            raise ValueError("Project storage must not redirect outside the root")
        database = storage_dir / "index.sqlite3"
        if not database.is_file() or database.is_symlink():
            raise ValueError("Run pie init/index first")
        return database

    def _connect(self) -> sqlite3.Connection:
        assert self._db_path is not None
        connection = sqlite3.connect(str(self._db_path), timeout=10.0)
        try:
            connection.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {self._TABLE} (
                    scene TEXT NOT NULL,
                    scope TEXT NOT NULL CHECK (scope IN ('selected','all')),
                    digest TEXT NOT NULL,
                    counts TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scene, scope)
                );
                CREATE TABLE IF NOT EXISTS {self._HISTORY_TABLE} (
                    scene TEXT NOT NULL,
                    scope TEXT NOT NULL CHECK (scope IN ('selected','all')),
                    version INTEGER NOT NULL,
                    digest TEXT NOT NULL,
                    counts TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (scene, scope, version)
                );
                """
            )
        except BaseException:
            connection.close()
            raise
        return connection

    def _load_store(self) -> None:
        assert self._db_path is not None
        loaded: OrderedDict[tuple[str, str], tuple[str, str, str]] = OrderedDict()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT scene, scope, digest, counts, updated_at FROM {self._TABLE} "
                "ORDER BY updated_at"
            ).fetchall()
        for scene, scope, digest, counts, updated_at in rows:
            if (not isinstance(scene, str) or not scene or len(scene) > 512
                    or scope not in ("selected", "all")
                    or not isinstance(digest, str) or len(digest) != 64
                    or not isinstance(counts, str) or not isinstance(updated_at, str)):
                raise ValueError("Invalid delta store entry")
            loaded[(scene, scope)] = (digest, counts, updated_at)
        for key in list(loaded)[: -self.capacity]:
            del loaded[key]
        with self._lock:
            self._fingerprints = loaded

    def _flush_store(self) -> None:
        """Best-effort persistence; failure degrades to memory-only."""
        db_path = self._db_path
        if db_path is None:
            return
        try:
            with closing(self._connect()) as connection:
                with connection:
                    # Upsert only this instance's own keys. Deleting the whole
                    # table would erase fingerprints written by other cache
                    # instances / processes sharing the same store; those rows
                    # are preserved and only pruned via _load_store's capacity
                    # handling when each instance loads them.
                    connection.executemany(
                        f"INSERT INTO {self._TABLE} "
                        "(scene, scope, digest, counts, updated_at) VALUES (?,?,?,?,?) "
                        "ON CONFLICT(scene, scope) DO UPDATE SET "
                        "digest=excluded.digest, counts=excluded.counts, "
                        "updated_at=excluded.updated_at",
                        [
                            (scene, scope, digest, counts, updated_at)
                            for (scene, scope), (digest, counts, updated_at)
                            in self._fingerprints.items()
                        ],
                    )
        except (OSError, ValueError, sqlite3.Error) as exc:
            # Persistence must never break the MCP call: keep the in-memory
            # baseline for this process and report the failure explicitly.
            self._persist_error = f"{type(exc).__name__}: {exc}"
            self._db_path = None

    def _append_history(self, scene: str, scope: str, digest: str,
                        counts_json: str, state: str) -> None:
        """Best-effort append of a fingerprint version to bounded history.

        Stores only hashes and metadata (never snapshot content); failure
        degrades to memory-only exactly like ``_flush_store``.
        """
        db_path = self._db_path
        if db_path is None:
            return
        try:
            with closing(self._connect()) as connection:
                # Serialize writers: BEGIN IMMEDIATE takes the write lock
                # before MAX(version) is read, so two processes appending
                # history for the same (scene, scope) cannot compute the same
                # next_version and collide on the primary key.
                connection.execute("BEGIN IMMEDIATE")
                try:
                    next_version = connection.execute(
                        f"SELECT COALESCE(MAX(version), 0) + 1 FROM {self._HISTORY_TABLE} "
                        "WHERE scene = ? AND scope = ?",
                        (scene, scope),
                    ).fetchone()[0]
                    connection.execute(
                        f"INSERT INTO {self._HISTORY_TABLE} "
                        "(scene, scope, version, digest, counts, state, created_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (scene, scope, next_version, digest, counts_json,
                         state, _utc_now()),
                    )
                    connection.execute(
                        f"DELETE FROM {self._HISTORY_TABLE} "
                        "WHERE scene = ? AND scope = ? "
                        "AND version <= ?",
                        (scene, scope, next_version - self._HISTORY_LIMIT),
                    )
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise
                connection.execute("COMMIT")
        except (OSError, ValueError, sqlite3.Error) as exc:
            self._persist_error = f"{type(exc).__name__}: {exc}"
            self._db_path = None

    def history(self, scene: str, scope: str, limit: int | None = None
                ) -> list[dict[str, Any]]:
        """Read-only accessor returning stored versions (hashes/metadata only).

        Most recent version first. Returns an empty list when persistence is
        unavailable or the key is unknown.
        """
        if type(scene) is not str or not scene or type(scope) is not str:
            return []
        db_path = self._db_path
        if db_path is None:
            return []
        query = (f"SELECT version, digest, counts, state, created_at "
                 f"FROM {self._HISTORY_TABLE} WHERE scene = ? AND scope = ? "
                 "ORDER BY version DESC")
        params: list[Any] = [scene, scope]
        if limit is not None:
            if type(limit) is not int or limit < 1:
                raise ValueError("limit must be a positive integer")
            query += " LIMIT ?"
            params.append(limit)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(query, params).fetchall()
        except (OSError, ValueError, sqlite3.Error):
            return []
        return [
            {"version": version, "digest": digest, "counts": counts,
             "state": state, "created_at": created_at}
            for version, digest, counts, state, created_at in rows
        ]

    @property
    def persistence_diagnostic(self) -> str | None:
        """Human-readable reason persistence was disabled, or None."""
        return self._persist_error

    # ------------------------------------------------------------------ observation
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
        with self._lock:
            objects = _entity_map(snapshot.get("objects"), "objects")
            materials = _entity_map(snapshot.get("materials"), "materials")
            omissions = snapshot.get("omissions", {})
            if not isinstance(omissions, dict):
                raise ValueError("Invalid omission metadata")
            complete = snapshot.get("complete") is True and not any(omissions.values())
            # A partial snapshot must never replace a complete baseline.
            fingerprint = _digest(snapshot)
            key = (scene, scope)
            previous = self._fingerprints.get(key)
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
                # Only fingerprints are retained (in memory and on disk), so the
                # change cannot be detailed here. Counts of the previous
                # baseline are available and are reported when parseable.
                try:
                    previous_counts = json.loads(previous[1])
                    if not isinstance(previous_counts, dict):
                        previous_counts = None
                except ValueError:
                    previous_counts = None
                if previous_counts is not None:
                    result["previous_counts"] = previous_counts
                result["note"] = ("Fingerprint-level delta; entity-level details "
                                  "require a fresh full inventory observation")
            encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            if len(encoded) > max_chars:
                # Do not update baseline when changes cannot be conveyed faithfully.
                return {"schema": DELTA_SCHEMA, "state": "BUDGET_EXCEEDED",
                        "scene": scene, "scope": scope, "digest": fingerprint,
                        "required_chars": len(encoded), "max_chars": max_chars,
                        "note": "Request a larger budget; current baseline was not changed"}
            counts_json = json.dumps(result["counts"], sort_keys=True, separators=(",", ":"))
            self._fingerprints[key] = (fingerprint, counts_json, _utc_now())
            self._fingerprints.move_to_end(key)
            while len(self._fingerprints) > self.capacity:
                self._fingerprints.popitem(last=False)
            self._flush_store()
            if self._db_path is not None:
                self._append_history(scene, scope, fingerprint, counts_json, state)
            return result
