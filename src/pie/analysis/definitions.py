"""Inventory of every binding a Python module creates (Etapa A).

A *definition* is one syntactic site that binds a name.  The same binding may be
bound several times (``x = 1`` then ``x = 2``): all those sites share one
``binding_key`` and are distinguished by ``line``/``col``, which is what lets a
reference point at a stable identity while remaining traceable to exact source.

Ownership is decided by the scope model, so ``global``/``nonlocal`` writes are
attributed to the module or closing function instead of the local body.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass

from pie.analysis.scopes import (
    CLASS_SCOPE,
    COMPREHENSION_SCOPE,
    FUNCTION_SCOPE,
    LAMBDA_SCOPE,
    MODULE_SCOPE,
    Scope,
    ScopeBuilder,
    ScopedVisitor,
    binding_key,
)

#: ``kind`` describes what the name *is* to a reader of the code.
KIND_CLASS = "class"
KIND_FUNCTION = "function"
KIND_METHOD = "method"
KIND_PARAMETER = "parameter"
KIND_VARIABLE = "variable"
KIND_CONSTANT = "constant"
KIND_ATTRIBUTE = "attribute"
#: ``self.x = ...`` inside a method: exists on instances only, never on the class.
KIND_INSTANCE_ATTRIBUTE = "instance_attribute"
KIND_IMPORT = "import"
KIND_EXCEPTION = "exception"


@dataclass(frozen=True)
class Definition:
    """One binding site, with a stable identity across re-indexing."""

    binding_key: str
    path: str
    name: str
    qualified_name: str
    scope_key: str
    scope_kind: str
    kind: str
    declared_by: str
    line: int
    col: int
    end_line: int
    end_col: int
    inferred_type: str | None = None
    #: For ``import`` bindings: the module that provides the value.
    source_module: str | None = None
    #: For ``from m import name``: the name as written in the source module.
    source_name: str | None = None
    #: For ``import m as alias``: the alias, which is also the local name.
    alias: str | None = None
    #: For ``def``/``class``: the scope its body owns.
    body_scope_key: str | None = None


_LITERAL_TYPES = {
    ast.Constant: None,  # resolved from the runtime value below
    ast.JoinedStr: "str",
    ast.List: "list",
    ast.Dict: "dict",
    ast.Set: "set",
    ast.Tuple: "tuple",
    ast.ListComp: "list",
    ast.SetComp: "set",
    ast.DictComp: "dict",
    ast.GeneratorExp: "generator",
    ast.Lambda: "function",
}


def infer_type(node: ast.AST | None) -> str | None:
    """Conservative literal inference.

    Only shapes the parser can prove without running anything are reported.
    Calls, attributes, subscripts and conditionals stay ``None``: guessing that
    ``open(...)`` yields a file or ``get()`` yields a dict would be fabrication.
    """
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        value = node.value
        if value is None:
            return "None"
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, complex):
            return "complex"
        if isinstance(value, str):
            return "str"
        if isinstance(value, bytes):
            return "bytes"
        return None
    if isinstance(node, ast.UnaryOp) and isinstance(node.operand, ast.Constant):
        return infer_type(node.operand)
    if isinstance(node, ast.BinOp):
        left, right = infer_type(node.left), infer_type(node.right)
        if left is not None and left == right and left in ("int", "float", "str", "bytes"):
            return left
        return None
    return _LITERAL_TYPES.get(type(node))


def annotation_name(node: ast.AST | None) -> str | None:
    """Rendered annotation, without evaluating it (``int``, ``list[str]``)."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - unparse is total for parsed trees
        return None


def _kind_for(scope: Scope, name: str, node: ast.AST | None) -> str:
    if scope.kind == MODULE_SCOPE:
        if name.isupper() and len(name) > 1 and name.replace("_", "").isalnum():
            return KIND_CONSTANT
        return KIND_VARIABLE
    if scope.kind == CLASS_SCOPE:
        return KIND_ATTRIBUTE
    return KIND_VARIABLE


def _declared_by(node: ast.AST | None, default: str) -> str:
    return type(node).__name__.lower() if node is not None else default


class DefinitionCollector(ScopedVisitor):
    """Walk a module once, emitting every binding site in source order."""

    def __init__(self, builder: ScopeBuilder, path: str) -> None:
        super().__init__(builder)
        self.path = path
        self.definitions: list[Definition] = []

    # -- helpers ---------------------------------------------------------
    def owning_scope(self, name: str) -> Scope:
        """Scope that actually owns ``name`` from the current position."""
        scope = self.current
        if name in scope.declared_global:
            return self.builder.module
        if name in scope.declared_nonlocal:
            owner = scope.nonlocal_owner.get(name)
            if owner is not None:
                return self.builder.scopes[owner]
        return scope

    def _emit(
        self,
        scope: Scope,
        name: str,
        kind: str,
        declared_by: str,
        node: ast.AST,
        *,
        inferred_type: str | None = None,
        source_module: str | None = None,
        source_name: str | None = None,
        alias: str | None = None,
        body_scope_key: str | None = None,
    ) -> None:
        line = getattr(node, "lineno", 0) or 0
        col = getattr(node, "col_offset", 0) or 0
        end_line = getattr(node, "end_lineno", None) or line
        end_col = getattr(node, "end_col_offset", None)
        if end_col is None:
            end_col = col + len(name)
        prefix = scope.qualified_name()
        qualified = f"{prefix}.{name}" if prefix else name
        self.definitions.append(
            Definition(
                binding_key=binding_key(self.path, scope.key, name),
                path=self.path,
                name=name,
                qualified_name=qualified,
                scope_key=scope.key,
                scope_kind=scope.kind,
                kind=kind,
                declared_by=declared_by,
                line=line,
                col=col,
                end_line=end_line,
                end_col=end_col,
                inferred_type=inferred_type,
                source_module=source_module,
                source_name=source_name,
                alias=alias,
                body_scope_key=body_scope_key,
            )
        )

    # -- statements ------------------------------------------------------
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        kind = KIND_METHOD if self.current.kind == CLASS_SCOPE else KIND_FUNCTION
        owner = self.owning_scope(node.name)
        self._emit(
            owner,
            node.name,
            kind,
            "def",
            node,
            inferred_type="function",
            body_scope_key=self.scope_of(node).key,
        )
        scope = self.scope_of(node)
        for argument in _argument_nodes(node.args):
            self._emit(
                scope,
                argument.arg,
                KIND_PARAMETER,
                "param",
                argument,
                inferred_type=annotation_name(argument.annotation),
            )
        super().visit_FunctionDef(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        owner = self.owning_scope(node.name)
        self._emit(
            owner,
            node.name,
            KIND_CLASS,
            "class",
            node,
            inferred_type="class",
            body_scope_key=self.scope_of(node).key,
        )
        super().visit_ClassDef(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        scope = self.scope_of(node)
        for argument in _argument_nodes(node.args):
            self._emit(
                scope,
                argument.arg,
                KIND_PARAMETER,
                "param",
                argument,
                inferred_type=annotation_name(argument.annotation),
            )
        super().visit_Lambda(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        inferred = infer_type(node.value)
        for target in node.targets:
            self.store_target(target, "assign", inferred)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.annotation)
        self.store_target(
            node.target,
            "annassign",
            annotation_name(node.annotation) or infer_type(node.value),
        )

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.value)
        # AugAssign reads the binding and writes it back: both are recorded.
        self.store_target(node.target, "augassign", infer_type(node.value))

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        self.store_target(node.target, "for", None)
        for statement in [*node.body, *node.orelse]:
            self.visit(statement)

    visit_AsyncFor = visit_For

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self.store_target(item.optional_vars, "with", None)
        for statement in node.body:
            self.visit(statement)

    visit_AsyncWith = visit_With

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self._emit(self.current, node.name, KIND_EXCEPTION, "except", node, inferred_type=None)
        for statement in node.body:
            self.visit(statement)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            self._emit(
                self.owning_scope(local),
                local,
                KIND_IMPORT,
                "import",
                node,
                source_module=alias.name,
                alias=alias.asname,
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        for alias in node.names:
            if alias.name == "*":
                continue
            local = alias.asname or alias.name
            self._emit(
                self.owning_scope(local),
                local,
                KIND_IMPORT,
                "from_import",
                node,
                source_module=module,
                source_name=alias.name,
                alias=alias.asname,
            )

    def _comprehension(self, node: ast.AST) -> None:
        """Comprehension targets are bindings of the comprehension scope."""
        scope = self.scope_of(node)
        for generator in node.generators:
            for name in _target_names(generator.target):
                self._emit(scope, name, KIND_VARIABLE, "comprehension", generator.target, inferred_type=None)
        super()._comprehension(node)

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_DictComp = _comprehension
    visit_GeneratorExp = _comprehension

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        scope = self.current
        while scope.kind == COMPREHENSION_SCOPE and scope.parent is not None:
            scope = scope.parent
        self._emit(scope, node.target.id, _kind_for(scope, node.target.id, node), "walrus", node.target,
                   inferred_type=infer_type(node.value))

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.pattern is not None:
            self.visit(node.pattern)
        if node.name:
            self._emit(self.current, node.name, _kind_for(self.current, node.name, node), "match", node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self._emit(self.current, node.name, _kind_for(self.current, node.name, node), "match", node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        for key in node.keys:
            self.visit(key)
        for pattern in node.patterns:
            self.visit(pattern)
        if node.rest:
            self._emit(self.current, node.rest, _kind_for(self.current, node.rest, node), "match", node)

    # -- targets ---------------------------------------------------------
    def store_target(self, target: ast.AST, declared_by: str, inferred: str | None) -> None:
        """Record a binding site, descending through destructuring patterns."""
        if isinstance(target, ast.Name):
            owner = self.owning_scope(target.id)
            self._emit(
                owner,
                target.id,
                _kind_for(owner, target.id, target),
                declared_by,
                target,
                inferred_type=inferred,
            )
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self.store_target(element, declared_by, None)
        elif isinstance(target, ast.Starred):
            self.store_target(target.value, declared_by, None)
        elif isinstance(target, ast.Attribute):
            self.visit(target.value)
            if isinstance(target.value, ast.Name) and target.value.id in ("self", "cls"):
                owner = self.builder.scopes[self.current.key]
                while owner.kind != CLASS_SCOPE and owner.parent is not None:
                    owner = owner.parent
                if owner.kind == CLASS_SCOPE:
                    # ``self.x`` writes an instance attribute: it shares the class
                    # namespace key but is not reachable as ``Class.x``.
                    self._emit(
                        owner,
                        target.attr,
                        KIND_INSTANCE_ATTRIBUTE,
                        f"instance_{declared_by}",
                        target,
                        inferred_type=inferred,
                    )
        elif isinstance(target, ast.Subscript):
            self.visit(target.value)
            self.visit(target.slice)


def _target_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        found: list[str] = []
        for element in target.elts:
            found.extend(_target_names(element))
        return found
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    return []


def _argument_nodes(args: ast.arguments) -> list[ast.arg]:
    collected = [*getattr(args, "posonlyargs", []), *args.args, *args.kwonlyargs]
    for extra in (args.vararg, args.kwarg):
        if extra is not None:
            collected.append(extra)
    return collected


def collect_definitions(tree: ast.AST, builder: ScopeBuilder, path: str) -> list[Definition]:
    collector = DefinitionCollector(builder, path)
    collector.visit(tree)
    return collector.definitions


def function_scopes(builder: ScopeBuilder) -> list[Scope]:
    """Named scopes that can act as a reference origin, innermost first."""
    return [
        scope
        for scope in builder.scopes.values()
        if scope.kind in (FUNCTION_SCOPE, LAMBDA_SCOPE, CLASS_SCOPE)
    ]
