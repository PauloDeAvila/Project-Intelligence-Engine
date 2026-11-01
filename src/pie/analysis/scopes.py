"""Lexical scope model, ownership analysis and scope-aware AST traversal.

Scope keys are deterministic, human readable strings derived from the syntactic
nesting of a file: ``module``, ``function:request``, ``class:Service.function:run``,
``function:index_project.comprehension@120``.  They identify a *static* scope,
never a runtime frame.  Sibling scopes sharing a name are suffixed ``#2``, ``#3``
in traversal order.

Nothing here inspects the interpreter, executes code or guesses types: it models
the rules CPython documents (LEGB lookup, PEP 3104 ``nonlocal``, PEP 572 walrus,
comprehension scoping) so the resolver can be proven correct rather than hopeful.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field

MODULE_SCOPE = "module"
CLASS_SCOPE = "class"
FUNCTION_SCOPE = "function"
LAMBDA_SCOPE = "lambda"
COMPREHENSION_SCOPE = "comprehension"

#: Scope kinds that can own a binding visible to nested scopes (PEP 3104 closers).
NESTABLE_SCOPES = frozenset({FUNCTION_SCOPE, LAMBDA_SCOPE, COMPREHENSION_SCOPE})

VERIFIED = "verified"
PROBABLE = "probable"
UNRESOLVED = "unresolved"
BUILTIN = "builtin"
RESOLUTIONS = (VERIFIED, PROBABLE, UNRESOLVED, BUILTIN)


@dataclass
class Scope:
    """One static scope: the names it owns plus its ``global``/``nonlocal`` declarations."""

    key: str
    kind: str
    name: str = ""
    parent: "Scope | None" = None
    bindings: set[str] = field(default_factory=set)
    declared_global: set[str] = field(default_factory=set)
    declared_nonlocal: set[str] = field(default_factory=set)
    nonlocal_owner: dict[str, str] = field(default_factory=dict)
    star_imports: set[str] = field(default_factory=set)

    def root(self) -> "Scope":
        current = self
        while current.parent is not None:
            current = current.parent
        return current

    def qualified_name(self) -> str:
        """Dotted path of the scope itself, e.g. ``Service.run`` (module -> ``''``)."""
        parts: list[str] = []
        current: "Scope | None" = self
        while current is not None and current.kind != MODULE_SCOPE:
            if current.name:
                parts.append(current.name)
            current = current.parent
        return ".".join(reversed(parts))


def scope_prefix(parent: "Scope | None", kind: str, name: str) -> str:
    segment = f"{kind}:{name}" if name else kind
    if parent is None or parent.kind == MODULE_SCOPE:
        return segment
    return f"{parent.key}.{segment}"


def unique_scope_key(existing: dict[str, Scope], parent: "Scope | None", kind: str, name: str = "") -> str:
    prefix = scope_prefix(parent, kind, name)
    key = prefix
    index = 1
    while key in existing:
        index += 1
        key = f"{prefix}#{index}"
    return key


def binding_key(path: str, scope_key: str, name: str) -> str:
    """Stable identity of a binding: relative path + owning scope + name.

    Deliberately not a database id: re-indexing replaces rows but keeps keys, so
    stored references and cross-module links stay comparable across runs.  A
    binding may have several definition sites (rebinding); they share one key.
    """
    return f"{path}::{scope_key}::{name}"


def module_binding_key(path: str, name: str) -> str:
    return binding_key(path, MODULE_SCOPE, name)


def file_binding_key(path: str) -> str:
    """Pseudo-binding for a whole module, the target of ``import pkg.mod``."""
    return f"file:{path}"


def is_file_binding(key: str) -> bool:
    return key.startswith("file:")


def split_binding_key(key: str) -> tuple[str, str, str]:
    path, _, rest = key.partition("::")
    scope, _, name = rest.rpartition("::")
    return path, scope, name


def lookup_chain(scope: Scope) -> list[Scope]:
    """Scopes searched for a name, in the order CPython searches them.

    A class body sees its own namespace plus enclosing function scopes, but a
    function defined inside a class body never sees the class namespace, so class
    scopes are skipped while walking outwards.  Builtins are the caller's problem:
    they are not project bindings.
    """
    chain = [scope]
    current = scope
    while current.parent is not None:
        current = current.parent
        if current.kind == CLASS_SCOPE:
            continue
        chain.append(current)
    return chain


def skipped_class_scopes(scope: Scope) -> list[str]:
    """Class scopes between ``scope`` and the module that the lookup chain skips."""
    skipped: list[str] = []
    current = scope
    while current.parent is not None:
        current = current.parent
        if current.kind == CLASS_SCOPE:
            skipped.append(current.key)
    return skipped


def enclosing_binder(scope: Scope, name: str) -> "Scope | None":
    """Nearest enclosing function-like scope owning ``name`` (PEP 3104 search)."""
    current = scope.parent
    while current is not None and current.kind != MODULE_SCOPE:
        if current.kind in NESTABLE_SCOPES and name in current.bindings:
            return current
        current = current.parent
    return None


def enclosing_class(scope: Scope) -> "Scope | None":
    """Nearest enclosing class scope, used to attribute ``self.x`` writes."""
    current = scope
    while current is not None:
        if current.kind == CLASS_SCOPE:
            return current
        current = current.parent
    return None


class ScopeBuilder(ast.NodeVisitor):
    """First pass: create one :class:`Scope` per lexical scope and record ownership.

    Ownership follows the compiler, not the reading order: any assignment in a
    function body makes the name local for the whole function, ``global`` and
    ``nonlocal`` redirect it, comprehension targets stay private to the
    comprehension while a walrus inside it escapes to the enclosing function.
    """

    def __init__(self) -> None:
        self.scopes: dict[str, Scope] = {}
        self.node_scopes: dict[int, Scope] = {}
        self.module = self._create(None, MODULE_SCOPE, "")
        self.stack: list[Scope] = [self.module]
        self.pending_nonlocal: list[tuple[Scope, tuple[str, ...]]] = []

    @property
    def current(self) -> Scope:
        return self.stack[-1]

    def _create(self, parent: Scope | None, kind: str, name: str, node: ast.AST | None = None) -> Scope:
        key = unique_scope_key(self.scopes, parent, kind, name)
        scope = Scope(key, kind, name, parent)
        self.scopes[key] = scope
        if node is not None:
            self.node_scopes[id(node)] = scope
        return scope

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.current.bindings.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in _argument_defaults(node.args):
            self.visit(default)
        for annotation in _annotations(node):
            self.visit(annotation)
        scope = self._create(self.current, FUNCTION_SCOPE, node.name, node)
        for argument in _argument_nodes(node.args):
            scope.bindings.add(argument.arg)
        self.stack.append(scope)
        for statement in node.body:
            self.visit(statement)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in _argument_defaults(node.args):
            self.visit(default)
        scope = self._create(self.current, LAMBDA_SCOPE, f"lambda@{node.lineno}", node)
        for argument in _argument_nodes(node.args):
            scope.bindings.add(argument.arg)
        self.stack.append(scope)
        self.visit(node.body)
        self.stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.current.bindings.add(node.name)
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in [*node.bases, *[keyword.value for keyword in node.keywords]]:
            self.visit(base)
        scope = self._create(self.current, CLASS_SCOPE, node.name, node)
        self.stack.append(scope)
        for statement in node.body:
            self.visit(statement)
        self.stack.pop()

    def _comprehension(self, node: ast.AST) -> None:
        generators = node.generators
        # The first iterable is evaluated in the enclosing scope (Python 3 rule).
        self.visit(generators[0].iter)
        scope = self._create(self.current, COMPREHENSION_SCOPE, f"comprehension@{node.lineno}", node)
        self.stack.append(scope)
        for index, generator in enumerate(generators):
            if index:
                self.visit(generator.iter)
            for target in _target_names(generator.target):
                scope.bindings.add(target)
            for condition in generator.ifs:
                self.visit(condition)
        for element in _comprehension_elements(node):
            self.visit(element)
        self.stack.pop()

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_DictComp = _comprehension
    visit_GeneratorExp = _comprehension

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for target in node.targets:
            self._bind_target(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.annotation)
        self._bind_target(node.target)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.visit(node.value)
        self._bind_target(node.target)

    def _bind_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self.current.bindings.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._bind_target(element)
        elif isinstance(target, ast.Starred):
            self._bind_target(target.value)
        elif isinstance(target, ast.Attribute):
            if _is_instance_attribute(target):
                owner = enclosing_class(self.current)
                if owner is not None:
                    owner.bindings.add(target.attr)
        elif isinstance(target, ast.Subscript):
            self.visit(target.value)

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        self._bind_target(node.target)
        for statement in [*node.body, *node.orelse]:
            self.visit(statement)

    visit_AsyncFor = visit_For

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._bind_target(item.optional_vars)
        for statement in node.body:
            self.visit(statement)

    visit_AsyncWith = visit_With

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self.current.bindings.add(node.name)
        for statement in node.body:
            self.visit(statement)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.current.bindings.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                self.current.star_imports.add("." * node.level + (node.module or ""))
            else:
                self.current.bindings.add(alias.asname or alias.name)

    def visit_Global(self, node: ast.Global) -> None:
        self.current.declared_global.update(node.names)
        self.module.bindings.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.current.declared_nonlocal.update(node.names)
        self.pending_nonlocal.append((self.current, tuple(node.names)))

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        scope = self.current
        while scope.kind == COMPREHENSION_SCOPE and scope.parent is not None:
            scope = scope.parent
        if isinstance(node.target, ast.Name):
            scope.bindings.add(node.target.id)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.current.bindings.add(target.id)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.pattern is not None:
            self.visit(node.pattern)
        if node.name:
            self.current.bindings.add(node.name)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self.current.bindings.add(node.name)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        for key in node.keys:
            self.visit(key)
        for pattern in node.patterns:
            self.visit(pattern)
        if node.rest:
            self.current.bindings.add(node.rest)

    def finish(self) -> None:
        """Resolve ``nonlocal`` owners once every binding in the file is known."""
        for scope, names in self.pending_nonlocal:
            for name in names:
                owner = enclosing_binder(scope, name)
                if owner is not None:
                    scope.nonlocal_owner[name] = owner.key


class ScopedVisitor(ast.NodeVisitor):
    """Traversal that keeps ``self.current`` pointing at the right static scope.

    Evaluation order is modelled explicitly because it decides ownership:
    decorators, defaults and annotations of a ``def`` run in the *enclosing*
    scope, the first iterable of a comprehension too, while the body, the
    parameters and the remaining clauses belong to the new scope.
    """

    def __init__(self, builder: ScopeBuilder) -> None:
        self.builder = builder
        self.stack: list[Scope] = [builder.module]

    @property
    def current(self) -> Scope:
        return self.stack[-1]

    def scope_of(self, node: ast.AST) -> Scope:
        return self.builder.node_scopes[id(node)]

    def on_scope_entered(self, node: ast.AST, scope: Scope) -> None:
        """Hook: called once a new scope becomes current, before its body."""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in _argument_defaults(node.args):
            self.visit(default)
        for annotation in _annotations(node):
            self.visit(annotation)
        scope = self.scope_of(node)
        self.stack.append(scope)
        self.on_scope_entered(node, scope)
        for statement in node.body:
            self.visit(statement)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in _argument_defaults(node.args):
            self.visit(default)
        scope = self.scope_of(node)
        self.stack.append(scope)
        self.on_scope_entered(node, scope)
        self.visit(node.body)
        self.stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in [*node.bases, *[keyword.value for keyword in node.keywords]]:
            self.visit(base)
        scope = self.scope_of(node)
        self.stack.append(scope)
        self.on_scope_entered(node, scope)
        for statement in node.body:
            self.visit(statement)
        self.stack.pop()

    def _comprehension(self, node: ast.AST) -> None:
        self.visit(node.generators[0].iter)
        scope = self.scope_of(node)
        self.stack.append(scope)
        self.on_scope_entered(node, scope)
        for index, generator in enumerate(node.generators):
            if index:
                self.visit(generator.iter)
            self.visit(generator.target)
            for condition in generator.ifs:
                self.visit(condition)
        for element in _comprehension_elements(node):
            self.visit(element)
        self.stack.pop()

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_DictComp = _comprehension
    visit_GeneratorExp = _comprehension


def _is_instance_attribute(node: ast.Attribute) -> bool:
    return isinstance(node.value, ast.Name) and node.value.id in ("self", "cls")


def _argument_nodes(args: ast.arguments) -> list[ast.arg]:
    collected = [*getattr(args, "posonlyargs", []), *args.args, *args.kwonlyargs]
    for extra in (args.vararg, args.kwarg):
        if extra is not None:
            collected.append(extra)
    return collected


def _argument_defaults(args: ast.arguments) -> list[ast.AST]:
    return [*args.defaults, *[default for default in args.kw_defaults if default is not None]]


def _annotations(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    found = [argument.annotation for argument in _argument_nodes(node.args) if argument.annotation is not None]
    if node.returns is not None:
        found.append(node.returns)
    return found


def _comprehension_elements(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.DictComp):
        return [node.key, node.value]
    return [node.elt]


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


def build_scopes(tree: ast.AST) -> ScopeBuilder:
    builder = ScopeBuilder()
    builder.visit(tree)
    builder.finish()
    return builder