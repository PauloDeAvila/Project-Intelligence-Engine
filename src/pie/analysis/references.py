"""Every place a name is read, written or deleted inside a module (Etapa A/B).

Usages are recorded *unresolved*: this module only states what the syntax says.
Deciding which binding a usage refers to is the resolver's job, so no guess can
hide here.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass

from pie.analysis.scopes import ScopeBuilder, ScopedVisitor

CONTEXT_LOAD = "load"
CONTEXT_STORE = "store"
CONTEXT_DEL = "del"


@dataclass(frozen=True)
class Usage:
    """One syntactic occurrence of a name, before resolution."""

    path: str
    name: str
    scope_key: str
    context: str
    line: int
    col: int
    #: Root name of a dotted access, e.g. ``mod`` in ``mod.CONST`` or ``self``.
    attribute_base: str | None = None
    #: Dotted tail after the root, e.g. ``CONST`` in ``mod.CONST``.
    attribute_path: str | None = None
    #: Human readable form, e.g. ``mod.CONST`` or ``CONST``.
    qualified_name: str = ""
    evidence: str = ""


class UsageCollector(ScopedVisitor):
    """Record loads, stores and deletes, including dotted and ``self.attr`` access."""

    def __init__(self, builder: ScopeBuilder, path: str) -> None:
        super().__init__(builder)
        self.path = path
        self.usages: list[Usage] = []

    def _add(
        self,
        node: ast.AST,
        name: str,
        context: str,
        attribute_base: str | None = None,
        attribute_path: str | None = None,
        qualified: str | None = None,
    ) -> None:
        scope = self.current
        if qualified is None:
            prefix = scope.qualified_name()
            qualified = f"{prefix}.{name}" if prefix else name
        if attribute_base is not None:
            evidence = f"{context} of attribute '{attribute_path}' on '{attribute_base}' inside {scope.key}"
        else:
            evidence = f"{context} of '{name}' inside {scope.key}"
        self.usages.append(
            Usage(
                path=self.path,
                name=name,
                scope_key=scope.key,
                context=context,
                line=getattr(node, "lineno", 0) or 0,
                col=getattr(node, "col_offset", 0) or 0,
                attribute_base=attribute_base,
                attribute_path=attribute_path,
                qualified_name=qualified,
                evidence=evidence,
            )
        )

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self._add(node, node.id, CONTEXT_LOAD)
        elif isinstance(node.ctx, ast.Store):
            self._add(node, node.id, CONTEXT_STORE)
        elif isinstance(node.ctx, ast.Del):
            self._add(node, node.id, CONTEXT_DEL)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        root, tail = _dotted(node)
        if root is None:
            self.generic_visit(node)
            return
        if isinstance(node.ctx, ast.Store):
            context = CONTEXT_STORE
        elif isinstance(node.ctx, ast.Del):
            context = CONTEXT_DEL
        else:
            context = CONTEXT_LOAD
        self._add(node, tail[-1], context, root, ".".join(tail), qualified=f"{root}.{'.'.join(tail)}")
        # The root name is itself read; record it once, at the first attribute.
        self._add(node, root, CONTEXT_LOAD)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        # ``x += 1`` reads then writes, but the AST only exposes a Store target.
        self.visit(node.value)
        target = node.target
        if isinstance(target, ast.Name):
            self._add(target, target.id, CONTEXT_LOAD)
            self._add(target, target.id, CONTEXT_STORE)
        elif isinstance(target, ast.Attribute):
            root, tail = _dotted(target)
            if root is None:
                self.generic_visit(target)
                return
            dotted = ".".join(tail)
            self._add(target, tail[-1], CONTEXT_LOAD, root, dotted, qualified=f"{root}.{dotted}")
            self._add(target, tail[-1], CONTEXT_STORE, root, dotted, qualified=f"{root}.{dotted}")
            self._add(target, root, CONTEXT_LOAD)
        else:
            self.visit(target)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._add(target, target.id, CONTEXT_DEL)
            else:
                self.visit(target)

    def visit_Global(self, node: ast.Global) -> None:
        """``global x`` declares intent; it is not a use of ``x``."""

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        """``nonlocal x`` declares intent; it is not a use of ``x``."""

    def visit_Import(self, node: ast.Import) -> None:
        """Imports are recorded as definitions, not as name usages."""

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Imports are recorded as definitions, not as name usages."""


def _dotted(node: ast.Attribute) -> tuple[str | None, list[str]]:
    """Split ``a.b.c`` into ``("a", ["b", "c"])``; ``None`` for computed bases."""
    tail: list[str] = [node.attr]
    current: ast.AST = node.value
    while isinstance(current, ast.Attribute):
        tail.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        tail.reverse()
        return current.id, tail
    return None, []


def collect_usages(tree: ast.AST, builder: ScopeBuilder, path: str) -> list[Usage]:
    collector = UsageCollector(builder, path)
    collector.visit(tree)
    return collector.usages