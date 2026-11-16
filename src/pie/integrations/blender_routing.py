"""Zero-token, fail-closed routing for explicit read-only Blender object lookups.

This component runs in the PIE Python process, not inside Blender or an LLM.
It never executes tools, builds Python code, infers missing names, or promotes
model output into evidence. Actual execution remains with the allowlisted MCP
bridge / executor. Ambiguous requests must be handled separately.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

EXACT_READ_TOOLS = ("pie_blender_get_object", "execute_blender_code")
MAX_OBJECT_NAME = 128


class ExactRouteError(ValueError):
    """An exact read-only route cannot be proved from the supplied metadata."""


@dataclass(frozen=True)
class ExactObjectRoute:
    tool_index: int
    target_index: int
    tool_name: str
    object_name: str
    strategy: str = "DETERMINISTIC_EXACT_MATCH_NO_MODEL"


def route_exact_object(
    tool_catalog: Sequence[dict[str, Any]],
    candidates: Sequence[str],
    requested_name: str,
) -> ExactObjectRoute:
    """Match explicit object name and safe read tool without generating tokens.

    Exact-name lookup is not a semantic problem. Prefer the PIE query tool
    over the constrained baseline code tool when both are advertised. Every
    argument is validated before returning a plan; no substring/fuzzy match.
    """
    if (not isinstance(requested_name, str) or not requested_name
            or len(requested_name) > MAX_OBJECT_NAME or "\x00" in requested_name):
        raise ExactRouteError("Invalid requested object name")
    if (not isinstance(candidates, (list, tuple)) or not candidates
            or len(candidates) > 128
            or any(not isinstance(name, str) or not name or len(name) > MAX_OBJECT_NAME
                   or "\x00" in name for name in candidates)
            or len(set(candidates)) != len(candidates)):
        raise ExactRouteError("Invalid or ambiguous object candidate catalog")
    matching = [i for i, name in enumerate(candidates) if name == requested_name]
    if len(matching) != 1:
        raise ExactRouteError("Exact requested object name is unavailable")
    if (not isinstance(tool_catalog, (list, tuple)) or not tool_catalog
            or len(tool_catalog) > 128):
        raise ExactRouteError("Invalid MCP tool catalog")
    names = [item.get("name") if isinstance(item, dict) else None
             for item in tool_catalog]
    if (any(not isinstance(name, str) or not name for name in names)
            or len(set(names)) != len(names)):
        raise ExactRouteError("Ambiguous or malformed MCP tool names")
    for allowed in EXACT_READ_TOOLS:
        if allowed in names:
            return ExactObjectRoute(
                tool_index=names.index(allowed),
                target_index=matching[0],
                tool_name=allowed,
                object_name=requested_name,
            )
    raise ExactRouteError("No approved exact read-only MCP tool is visible")
