import ast
from pathlib import Path

from pie.core.models import ImportRecord, SymbolRecord


def parse_python(path: Path, relative_path: str) -> tuple[list[SymbolRecord], list[ImportRecord], str | None]:
    try:
        return parse_python_content(path.read_bytes(), relative_path)
    except (OSError, UnicodeDecodeError) as exc:
        return [], [], type(exc).__name__


def parse_python_content(content: bytes, relative_path: str) -> tuple[list[SymbolRecord], list[ImportRecord], str | None]:
    try:
        tree = ast.parse(content.decode("utf-8"), filename=relative_path)
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        return [], [], type(exc).__name__

    symbols: list[SymbolRecord] = []
    imports: list[ImportRecord] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope: list[str] = []
            self.kind_scope: list[str] = []

        def _symbol(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> None:
            name = node.name
            qualified = ".".join((*self.scope, name))
            symbols.append(SymbolRecord(qualified, name, kind, relative_path, node.lineno, node.end_lineno or node.lineno, node.col_offset, getattr(node, "end_col_offset", node.col_offset)))
            self.scope.append(name)
            self.kind_scope.append(kind)
            self.generic_visit(node)
            self.kind_scope.pop()
            self.scope.pop()

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self._symbol(node, "class")

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._symbol(node, "method" if self.kind_scope and self.kind_scope[-1] == "class" else "function")

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._symbol(node, "method" if self.kind_scope and self.kind_scope[-1] == "class" else "function")

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                imports.append(ImportRecord(alias.name, None, alias.asname, relative_path, node.lineno))

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            module = "." * node.level + (node.module or "")
            for alias in node.names:
                imports.append(ImportRecord(module, alias.name, alias.asname, relative_path, node.lineno))

    Visitor().visit(tree)
    return symbols, imports, None

