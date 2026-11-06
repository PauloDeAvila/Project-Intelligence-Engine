"""Conservative language adapters for the project inventory.

The adapters extract only obvious declarations and imports. They do not claim
type resolution, call graphs, or engine semantics. Python keeps its AST parser
and analysis pipeline unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pie.core.models import ImportRecord, SymbolRecord
from pie.indexing.python_ast import parse_python_content

LANGUAGES: dict[str, str] = {
    ".py": "python", ".c": "c", ".h": "c_header", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp",
    ".hpp": "cpp_header", ".hxx": "cpp_header", ".m": "objective_c", ".mm": "objective_cpp",
    ".cs": "csharp", ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".hx": "haxe", ".gd": "gdscript", ".js": "javascript",
    ".ts": "typescript", ".shader": "shader", ".glsl": "shader", ".comp": "shader", ".metal": "shader",
    ".wgsl": "shader", ".gdshader": "shader", ".hlsl": "shader", ".vert": "shader", ".frag": "shader",
    ".d3d11": "shader", ".cso": "shader_binary", ".spirv": "shader_binary", ".usf": "unreal_shader", ".ush": "unreal_shader", ".godot": "godot_project",
    ".tscn": "godot_scene", ".tres": "godot_resource", ".uproject": "unreal_project", ".uplugin": "unreal_plugin",
    ".arm": "armorpaint_asset", ".blend": "blender_asset", ".obj": "mesh_obj",
    ".json": "json", ".xml": "xml", ".yml": "yaml", ".yaml": "yaml", ".toml": "toml",
    ".vcxproj": "msbuild_project", ".sln": "visual_studio_solution", ".slnx": "visual_studio_solution",
}

TEXT_LANGUAGES = {
    "c", "c_header", "cpp", "cpp_header", "objective_c", "objective_cpp", "csharp", "java", "haxe",
    "gdscript", "javascript", "typescript", "kotlin", "shader", "unreal_shader",
}

_DECLARATION = re.compile(
    r"(?m)^\s*(?:(?:public|private|protected|internal|static|abstract|virtual|override|inline|extern|async|export|default|final)\s+)*"
    r"(?P<kind>class|struct|interface|enum|namespace|function|func|fn)\s+(?P<name>[A-Za-z_$][\w$]*)"
)
_FUNCTION = re.compile(
    r"(?m)^\s*(?:(?:public|private|protected|internal|static|virtual|override|inline|async|export|final|const|def)\s+)*"
    r"(?:[A-Za-z_$][\w$:*&<>\[\], .-]*\s+)?(?P<name>[A-Za-z_$~][\w$]*)\s*\([^\n;{}]*\)\s*(?:const\s*)?(?:\{|=>)"
)
_IMPORTS = {
    "c": re.compile(r"(?m)^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]"),
    "c_header": re.compile(r"(?m)^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]"),
    "cpp": re.compile(r"(?m)^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]"),
    "cpp_header": re.compile(r"(?m)^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]"),
    "objective_c": re.compile(r"(?m)^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]"),
    "objective_cpp": re.compile(r"(?m)^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]"),
    "csharp": re.compile(r"(?m)^\s*using\s+([A-Za-z_][\w.]*)\s*;"),
    "java": re.compile(r"(?m)^\s*import\s+([A-Za-z_][\w.]*)\s*;"),
    "haxe": re.compile(r"(?m)^\s*import\s+([A-Za-z_][\w.]*)\s*;"),
    "kotlin": re.compile(r"(?m)^\s*import\s+([A-Za-z_][\w.]*)"),
    "gdscript": re.compile(r"(?m)^\s*extends\s+([^\s]+)"),
    "javascript": re.compile(r"(?m)^\s*import\s+(?:[^;]*?\s+from\s+)?[\"']([^\"']+)[\"']"),
    "typescript": re.compile(r"(?m)^\s*import\s+(?:[^;]*?\s+from\s+)?[\"']([^\"']+)[\"']"),
}


@dataclass(frozen=True)
class ParseResult:
    symbols: list[SymbolRecord]
    imports: list[ImportRecord]
    status: str
    diagnostics: list[str]
    capabilities: tuple[str, ...]
    column_encoding: str = "utf8-byte"


def _line_col(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    start = text.rfind("\n", 0, offset) + 1
    return line, len(text[start:offset].encode("utf-8"))


def _generic_parse(content: bytes, relative_path: str, language: str) -> ParseResult:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return ParseResult([], [], "parser_unavailable", ["source is not valid UTF-8"], ())
    symbols: list[SymbolRecord] = []
    matches = list(_DECLARATION.finditer(text)) + list(_FUNCTION.finditer(text))
    seen: set[tuple[str, int]] = set()
    for match in matches:
        name = match.group("name")
        kind = match.groupdict().get("kind") or "function"
        line, col = _line_col(text, match.start("name"))
        if (name, line) in seen:
            continue
        seen.add((name, line))
        symbols.append(SymbolRecord(name, name, kind, relative_path, line, line, col, col + len(name.encode("utf-8"))))
    imports: list[ImportRecord] = []
    pattern = _IMPORTS.get(language)
    if pattern:
        for match in pattern.finditer(text):
            imports.append(ImportRecord(match.group(1), None, None, relative_path, text.count("\n", 0, match.start()) + 1))
    symbols.sort(key=lambda item: (item.start_line, item.start_col, item.name))
    return ParseResult(symbols, imports, "parsed", [], ("symbols", "imports"))


def parse_content(content: bytes, relative_path: str, language: str | None) -> ParseResult:
    if language == "python":
        symbols, imports, error = parse_python_content(content, relative_path)
        return ParseResult(symbols, imports, "parse_error" if error else "parsed", [error] if error else [], ("symbols", "imports"))
    if language in TEXT_LANGUAGES:
        return _generic_parse(content, relative_path, language)
    if language:
        return ParseResult([], [], "metadata_only", [], ("file_inventory",))
    return ParseResult([], [], "parser_unavailable", ["language not identified"], ())
