"""Name resolution: turns syntactic usages into evidence-backed references (Etapa B).

Three verdicts exist and only the first may be treated as fact:

``verified``
    A project binding is reachable by rules the language guarantees: lexical
    scope, ``global``/``nonlocal`` redirection, an indexed module import, or an
    attribute owned by the class whose method is executing.
``probable``
    Exactly one candidate exists, but reaching it relies on an assumption the
    parser cannot prove, such as a ``from module import *`` star import.
``unresolved``
    Nothing, or more than one thing, can be proven: external modules, attributes
    of unknown types, relative imports, dotted chains through unknown objects.
    Fabricating a target here is the failure mode this layer exists to prevent.

``builtin`` is a fourth, non-project verdict used so ``print`` is not reported as
a missing symbol.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field

from pie.analysis.definitions import (
    KIND_ATTRIBUTE,
    KIND_INSTANCE_ATTRIBUTE,
    Definition,
    collect_definitions,
)
from pie.analysis.references import Usage, collect_usages
from pie.analysis.scopes import (
    CLASS_SCOPE,
    COMPREHENSION_SCOPE,
    FUNCTION_SCOPE,
    LAMBDA_SCOPE,
    MODULE_SCOPE,
    PROBABLE,
    Scope,
    ScopeBuilder,
    UNRESOLVED,
    VERIFIED,
    build_scopes,
    enclosing_class,
    file_binding_key,
    lookup_chain,
    skipped_class_scopes,
)

BUILTIN = "builtin"

MAX_IMPORT_DEPTH = 8

#: Names the interpreter provides.  Never project references, never "missing".
BUILTIN_NAMES = frozenset(
    """
    __build_class__ __debug__ __doc__ __file__ __import__ __loader__ __name__
    __package__ __spec__ abs aiter all anext any ascii bin bool breakpoint
    bytearray bytes callable chr classmethod compile complex copyright credits
    delattr dict dir divmod enumerate eval exec exit filter float format
    frozenset getattr globals hasattr hash help hex id input int isinstance
    issubclass iter len license list locals map max memoryview min next object
    oct open ord pow print property quit range repr reversed round set setattr
    slice sorted staticmethod str sum super tuple type vars zip
    ArithmeticError AssertionError AttributeError BaseException BlockingIOError
    BrokenPipeError BufferError BytesWarning ChildProcessError ConnectionAbortedError
    ConnectionError ConnectionRefusedError ConnectionResetError DeprecationWarning
    EOFError EncodingWarning EnvironmentError Exception ExceptionGroup False
    FileExistsError FileNotFoundError FloatingPointError FutureWarning
    GeneratorExit ImportError ImportWarning IndentationError IndexError
    InterruptedError IsADirectoryError KeyError KeyboardInterrupt LookupError
    MemoryError ModuleNotFoundError NameError NotADirectoryError NotImplemented
    NotImplementedError OSError OverflowError PendingDeprecationWarning
    PermissionError ProcessLookupError RecursionError ReferenceError
    ResourceWarning RuntimeError RuntimeWarning StopAsyncIteration StopIteration
    SyntaxError SyntaxWarning SystemError SystemExit TabError True TypeError
    UnboundLocalError UnicodeDecodeError UnicodeEncodeError UnicodeError
    UnicodeTranslateError UnicodeWarning UserWarning ValueError Warning
    ZeroDivisionError
    """.split()
)


#: Scope key of the synthetic module binding; it is deliberately outside every
#: lexical scope so ``import pkg.mod`` cannot shadow a real name called ``mod``.
FILE_SCOPE = "<file>"


@dataclass
class ModuleFacts:
    """Everything the resolver needs to know about one module, without its AST."""

    path: str
    dotted_names: tuple[str, ...]
    #: ``(scope_key, name) -> definition sites`` in source order.
    definitions: dict[tuple[str, str], list[Definition]] = field(default_factory=dict)
    star_imports: tuple[str, ...] = ()
    #: Synthetic binding standing for the module itself (target of ``import pkg.mod``).
    module_binding: Definition | None = None

    def sites(self, scope_key: str, name: str) -> list[Definition]:
        return self.definitions.get((scope_key, name), [])


@dataclass(frozen=True)
class Reference:
    """A usage with the verdict the resolver reached about it."""

    path: str
    name: str
    qualified_name: str
    scope_key: str
    context: str
    line: int
    col: int
    origin_symbol: str | None
    resolution: str
    evidence: str
    #: Root name of a dotted access (``mod`` in ``mod.CONST``); ``None`` for plain names.
    attribute_base: str | None = None
    attribute_path: str | None = None
    target_binding_key: str | None = None
    target_path: str | None = None
    target_name: str | None = None
    target_line: int | None = None
    #: Import binding through which a cross-module reference reached its target.
    via: str | None = None


@dataclass
class ModuleAnalysis:
    """Facts extracted from one file, plus the scopes needed to resolve them."""

    path: str
    builder: ScopeBuilder
    definitions: list[Definition]
    usages: list[Usage]
    tree: ast.AST | None = None

    def facts(self) -> ModuleFacts:
        names = dotted_module_names(self.path)
        facts = ModuleFacts(self.path, names)
        facts.module_binding = module_definition(self.path)
        for definition in self.definitions:
            if definition.scope_key == FILE_SCOPE:
                continue
            facts.definitions.setdefault((definition.scope_key, definition.name), []).append(definition)
        for sites in facts.definitions.values():
            sites.sort(key=lambda site: (site.line, site.col))
        facts.star_imports = tuple(sorted(self.builder.module.star_imports))
        return facts


def dotted_module_names(path: str) -> tuple[str, ...]:
    """Every dotted name this file could be imported as, most specific first.

    The index has no ``sys.path``, so ``src/pkg/mod.py`` registers as both
    ``src.pkg.mod`` and ``pkg.mod``; ``pkg/__init__.py`` registers as ``pkg``.
    """
    if not path.endswith(".py"):
        return ()
    parts = [part for part in path[:-3].replace("\\", "/").split("/") if part]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return ()
    return tuple(".".join(parts[start:]) for start in range(len(parts)))


def analyze_module(tree: ast.AST, path: str) -> ModuleAnalysis:
    builder = build_scopes(tree)
    analysis = ModuleAnalysis(
        path=path,
        builder=builder,
        definitions=collect_definitions(tree, builder, path),
        usages=collect_usages(tree, builder, path),
        tree=tree,
    )
    # Persist a row for the module itself so ``import pkg.mod`` can point at it
    # and every cross-file target references a definition that really exists.
    binding = module_definition(path)
    if binding is not None:
        analysis.definitions.insert(0, binding)
    return analysis


def module_definition(path: str) -> Definition | None:
    """Synthetic definition representing ``path`` as an importable module."""
    names = dotted_module_names(path)
    if not names:
        return None
    return Definition(
        binding_key=file_binding_key(path),
        path=path,
        name=names[0],
        qualified_name=names[0],
        scope_key=FILE_SCOPE,
        scope_kind="file",
        kind="module",
        declared_by="module",
        line=1,
        col=0,
        end_line=1,
        end_col=0,
    )


def analyze_source(source: str | bytes, path: str) -> ModuleAnalysis:
    if isinstance(source, bytes):
        source = source.decode("utf-8-sig")
    return analyze_module(ast.parse(source, filename=path), path)


def _effective_site(sites: list[Definition], line: int) -> Definition | None:
    """Last definition at or before ``line``; the first one otherwise.

    Choosing by position keeps ``x = 1`` / ``x = 2`` honest: a read after the
    rebinding is attributed to the second site while sharing one binding key.
    """
    if not sites:
        return None
    chosen = None
    for site in sites:
        if site.line <= line:
            chosen = site
        else:
            break
    return chosen or sites[0]


def enclosing_symbol_name(scope: Scope) -> str | None:
    """Dotted name of the innermost named scope (``Service.run``), else ``None``."""
    current: Scope | None = scope
    while current is not None:
        if current.kind in (CLASS_SCOPE, FUNCTION_SCOPE, LAMBDA_SCOPE) and current.name:
            return current.qualified_name()
        current = current.parent
    return None


class Resolver:
    """Resolve one module's usages against every module of the project."""

    def __init__(self, facts: list[ModuleFacts]) -> None:
        self.by_path = {module.path: module for module in facts}
        self.by_dotted: dict[str, list[ModuleFacts]] = {}
        for module in facts:
            for name in module.dotted_names:
                self.by_dotted.setdefault(name, []).append(module)

    # -- entry points ----------------------------------------------------
    def resolve_module(self, analysis: ModuleAnalysis) -> list[Reference]:
        facts = analysis.facts()
        return [self.resolve(usage, analysis, facts) for usage in analysis.usages]

    def resolve_all(self, analyses: list[ModuleAnalysis]) -> list[Reference]:
        facts = [analysis.facts() for analysis in analyses]
        resolver = Resolver(facts)
        references: list[Reference] = []
        for analysis, module_facts in zip(analyses, facts):
            references.extend(resolver.resolve(usage, analysis, module_facts) for usage in analysis.usages)
        return references

    def resolve(self, usage: Usage, analysis: ModuleAnalysis, facts: ModuleFacts) -> Reference:
        scope = analysis.builder.scopes[usage.scope_key]
        origin = enclosing_symbol_name(scope)
        if usage.attribute_base is not None:
            target, resolution, evidence, via = self._resolve_attribute(usage, scope, facts)
        else:
            target, resolution, evidence, via = self._resolve_name(usage.name, scope, usage.line, facts)
        return Reference(
            path=usage.path,
            name=usage.name,
            qualified_name=usage.qualified_name,
            scope_key=usage.scope_key,
            context=usage.context,
            line=usage.line,
            col=usage.col,
            origin_symbol=origin,
            resolution=resolution,
            evidence=evidence,
            attribute_base=usage.attribute_base,
            attribute_path=usage.attribute_path,
            target_binding_key=target.binding_key if target else None,
            target_path=target.path if target else None,
            target_name=target.name if target else None,
            target_line=target.line if target else None,
            via=via,
        )

    # -- lookup ----------------------------------------------------------
    def _lookup(self, name: str, scope: Scope) -> tuple[Scope | None, str]:
        """Which scope owns ``name`` as seen from ``scope`` (LEGB minus builtins)."""
        if name in scope.declared_global:
            root = scope.root()
            return (root, "declared global") if name in root.bindings else (None, "declared global but unbound")
        if name in scope.declared_nonlocal:
            owner_key = scope.nonlocal_owner.get(name)
            if owner_key is None:
                return None, "declared nonlocal without enclosing binding"
            owner = self._find_scope(scope, owner_key)
            return (owner, "declared nonlocal") if owner else (None, "declared nonlocal outside this file")
        for candidate in lookup_chain(scope):
            if name in candidate.bindings:
                return candidate, "lexical scope"
        skipped = skipped_class_scopes(scope)
        if skipped:
            return None, f"class scope {skipped[0]} is not in the lookup chain for functions"
        return None, "no lexical binding"

    @staticmethod
    def _find_scope(scope: Scope, key: str) -> Scope | None:
        current: Scope | None = scope
        while current is not None:
            if current.key == key:
                return current
            current = current.parent
        return None

    def _resolve_name(
        self, name: str, scope: Scope, line: int, facts: ModuleFacts
    ) -> tuple[Definition | None, str, str, str | None]:
        owner, why = self._lookup(name, scope)
        if owner is not None:
            sites = facts.sites(owner.key, name)
            site = _effective_site(sites, line)
            if owner.kind == MODULE_SCOPE and site is not None and site.kind == "import":
                if site.source_name is None:
                    return self._resolve_module_import(site, name)
                followed = self._follow_import(site, 0, frozenset())
                if followed is not None:
                    target, resolution, evidence = followed
                    return target, resolution, evidence, site.binding_key
                return None, UNRESOLVED, (
                    f"'{name}' imports {site.source_name!r} from {site.source_module!r}: "
                    + self._import_failure(site)
                ), site.binding_key
            if site is None:
                return None, UNRESOLVED, f"{why}: '{name}' is bound in {owner.key} without a definition site", None
            return site, VERIFIED, f"{why}: '{name}' belongs to {owner.key} (defined line {site.line})", None
        if name in BUILTIN_NAMES:
            return None, BUILTIN, f"'{name}' is provided by the interpreter", None
        for star_module in facts.star_imports:
            candidates = self._modules_for(star_module)
            if len(candidates) == 1 and candidates[0].sites(MODULE_SCOPE, name):
                site = _effective_site(candidates[0].sites(MODULE_SCOPE, name), 10**9)
                return site, PROBABLE, (
                    f"star import from '{star_module}' is the only candidate for '{name}'"
                ), None
        return None, UNRESOLVED, f"{why}: '{name}' is not bound in any visible project scope", None

    def _import_failure(self, site: Definition) -> str:
        """Explain precisely why an import chain could not be followed."""
        candidates = self._modules_for(site.source_module or "")
        if not candidates:
            return "that module is not indexed"
        if len(candidates) > 1:
            paths = ", ".join(sorted(module.path for module in candidates))
            return f"the module name is ambiguous between {paths}"
        module = candidates[0]
        if not module.sites(MODULE_SCOPE, site.source_name or ""):
            if self._submodule(site.source_module or "", site.source_name or "") is None:
                return f"'{site.source_name}' is not a module-level name of {module.path}"
            return "the import chain does not terminate in a project definition"
        return "the import chain does not terminate in a project definition"

    def _resolve_module_import(
        self, site: Definition, name: str
    ) -> tuple[Definition | None, str, str, str | None]:
        """``import pkg.mod`` / ``import pkg.mod as alias``: the value is the module."""
        candidates = self._modules_for(site.source_module or "")
        if len(candidates) == 1 and candidates[0].module_binding is not None:
            binding = candidates[0].module_binding
            return binding, VERIFIED, (
                f"'{name}' is the module {binding.path} imported at line {site.line}"
            ), None
        reason = "not indexed" if not candidates else "ambiguous"
        return None, UNRESOLVED, f"'{name}' imports {site.source_module!r}, which is {reason}", None

    # -- attributes ------------------------------------------------------
    def _resolve_attribute(
        self, usage: Usage, scope: Scope, facts: ModuleFacts
    ) -> tuple[Definition | None, str, str, str | None]:
        base = usage.attribute_base or ""
        tail = usage.attribute_path or usage.name
        if base in ("self", "cls"):
            owner = enclosing_class(scope)
            if owner is None:
                return None, UNRESOLVED, f"{base}.{tail} used outside any class", None
            return self._resolve_self_attribute(usage, owner, base, tail, facts)

        base_owner, why = self._lookup(base, scope)
        if base_owner is None:
            if base in BUILTIN_NAMES:
                return None, UNRESOLVED, f"'{base}' is a builtin; its attributes are not project bindings", None
            return None, UNRESOLVED, f"{why}: cannot determine what '{base}' is", None
        if base_owner.kind != MODULE_SCOPE:
            return None, UNRESOLVED, (
                f"'{base}' is a local binding in {base_owner.key}; its type is unknown statically"
            ), None

        site = _effective_site(facts.sites(MODULE_SCOPE, base), usage.line)
        if site is None:
            return None, UNRESOLVED, f"'{base}' has no module-level definition site", None
        if site.kind == "class":
            return self._resolve_class_attribute(site, usage, base, tail)
        if site.kind != "import":
            return None, UNRESOLVED, (
                f"'{base}' is a module-level {site.kind}, not a module or class; "
                f"'{base}.{tail}' cannot be resolved statically"
            ), None
        return self._resolve_imported_attribute(site, usage, base, tail)

    def _resolve_self_attribute(
        self,
        usage: Usage,
        owner: Scope,
        base: str,
        tail: str,
        facts: ModuleFacts,
    ) -> tuple[Definition | None, str, str, str | None]:
        """``self.x`` / ``cls.x`` against the enclosing class body.

        ``self.x`` reads the instance namespace first and falls back to the class
        body; ``cls.x`` never reaches an instance attribute.  When both a class
        attribute and an instance attribute share the name, static analysis cannot
        prove which one a ``self.x`` read observes, so the verdict is ``probable``
        instead of ``verified``.
        """
        sites = facts.sites(owner.key, usage.name)
        class_sites = [item for item in sites if item.kind == KIND_ATTRIBUTE]
        instance_sites = [item for item in sites if item.kind == KIND_INSTANCE_ATTRIBUTE]

        if base == "cls":
            if not class_sites:
                if instance_sites:
                    return None, UNRESOLVED, (
                        f"cls.{tail}: '{usage.name}' is only an instance attribute of {owner.name}; "
                        "the class object does not expose it"
                    ), None
                return None, UNRESOLVED, (
                    f"cls.{tail}: class {owner.name} declares no class-level attribute '{usage.name}' "
                    "in this module"
                ), None
            site = _effective_site(class_sites, 10**9)
            return site, PROBABLE, (
                f"cls.{tail} is the statically declared class-level attribute '{site.name}' of {owner.name} "
                f"(line {site.line})"
            ), None

        if class_sites and instance_sites:
            site = _effective_site(instance_sites, usage.line) or instance_sites[0]
            return site, PROBABLE, (
                f"self.{tail}: {owner.name} declares both a class attribute and an instance "
                f"attribute '{usage.name}'; the read resolves to the instance namespace at runtime "
                f"(instance site line {site.line})"
            ), None
        if class_sites:
            site = _effective_site(class_sites, 10**9)
            return site, PROBABLE, (
                f"self.{tail} is the statically declared class-level attribute '{site.name}' of {owner.name} "
                f"(line {site.line}); no instance attribute shadows it"
            ), None
        if instance_sites:
            site = _effective_site(instance_sites, usage.line) or instance_sites[0]
            return site, PROBABLE, (
                f"self.{tail} is the statically identified instance attribute '{site.name}' of {owner.name} "
                f"(assigned at line {site.line})"
            ), None
        return None, UNRESOLVED, (
            f"{base}.{tail}: class {owner.name} declares no attribute '{usage.name}' in this module"
        ), None

    def _resolve_class_attribute(
        self, class_site: Definition, usage: Usage, base: str, tail: str
    ) -> tuple[Definition | None, str, str, str | None]:
        """``Class.attr`` where ``Class`` is a class defined in this module."""
        if "." in tail:
            return None, UNRESOLVED, f"'{base}.{tail}' crosses an attribute of unknown type", None
        body_scope = class_site.body_scope_key
        if body_scope is None:
            return None, UNRESOLVED, f"'{base}' is a class without a recorded body scope", None
        sites = self._sites_in_scope(class_site.path, body_scope, usage.name)
        candidates = [item for item in sites if item.kind == KIND_ATTRIBUTE]
        if not candidates:
            if any(item.kind == KIND_INSTANCE_ATTRIBUTE for item in sites):
                return None, UNRESOLVED, (
                    f"'{base}.{tail}': '{usage.name}' is only an instance attribute of "
                    f"{class_site.qualified_name}; the class object does not expose it"
                ), None
            return None, UNRESOLVED, (
                f"'{base}.{tail}' is not a class-level attribute of {class_site.qualified_name}"
            ), None
        site = _effective_site(candidates, 10**9)
        return site, PROBABLE, (
            f"{base}.{tail} is the statically declared class-level attribute of {class_site.qualified_name} "
            f"(line {site.line})"
        ), None

    def _sites_in_scope(self, path: str, scope_key: str, name: str) -> list[Definition]:
        module = self.by_path.get(path)
        return module.sites(scope_key, name) if module else []

    def _resolve_imported_attribute(
        self, site: Definition, usage: Usage, base: str, tail: str
    ) -> tuple[Definition | None, str, str, str | None]:
        """``mod.attr`` / ``alias.attr`` where ``mod`` is an indexed module import."""
        dotted = f"{base}.{tail}"
        if site.source_name is not None:
            # ``from pkg import sub``: ``sub`` may be a module, so ``sub.x`` is
            # looked up inside ``pkg.sub`` rather than inside ``pkg``.
            submodule = self._submodule(site.source_module or "", site.source_name)
            if submodule is not None:
                return self._attribute_of_module(submodule, tail, dotted, site.binding_key)
        module_dotted = site.source_module or ""
        if site.alias:
            # ``import pkg.mod as alias``: the alias replaces the whole path.
            full = module_dotted + dotted[len(base):]
        else:
            full = dotted
        if full != module_dotted and not full.startswith(module_dotted + "."):
            return None, UNRESOLVED, (
                f"'{dotted}' does not belong to imported module '{module_dotted}'"
            ), site.binding_key
        candidates = self._modules_for(module_dotted)
        if len(candidates) != 1:
            reason = "not indexed" if not candidates else "ambiguous"
            return None, UNRESOLVED, f"module '{module_dotted}' is {reason}", site.binding_key
        module = candidates[0]
        remainder = full[len(module_dotted):].lstrip(".")
        if not remainder:
            binding = module.module_binding
            return binding, VERIFIED, f"'{dotted}' is the module {module.path} itself", site.binding_key
        return self._attribute_of_module(module, remainder, dotted, site.binding_key)

    def _attribute_of_module(
        self, module: ModuleFacts, remainder: str, dotted: str, via: str | None
    ) -> tuple[Definition | None, str, str, str | None]:
        """Resolve ``base.remainder`` as a module-level name of ``module``."""
        if "." in remainder:
            return None, UNRESOLVED, (
                f"'{dotted}' crosses an attribute of unknown type inside {module.path}"
            ), via
        target = _effective_site(module.sites(MODULE_SCOPE, remainder), 10**9)
        if target is None:
            return None, UNRESOLVED, (
                f"'{remainder}' is not a module-level name of {module.path}"
            ), via
        if target.kind == "import":
            followed = self._follow_import(target, 0, frozenset())
            if followed is not None:
                resolved, resolution, evidence = followed
                return resolved, resolution, f"{dotted} -> {evidence}", via
        return target, VERIFIED, f"{dotted} resolves to {target.binding_key} (line {target.line})", via

    def _submodule(self, package: str, name: str) -> ModuleFacts | None:
        """The indexed module ``package.name``, when exactly one file claims it."""
        if not package or not name:
            return None
        candidates = self._modules_for(f"{package}.{name}")
        return candidates[0] if len(candidates) == 1 else None

    # -- imports ---------------------------------------------------------
    def _modules_for(self, dotted: str) -> list[ModuleFacts]:
        """Modules reachable by ``dotted``; more than one means ambiguity."""
        if not dotted:
            return []
        found: list[ModuleFacts] = []
        seen: set[str] = set()
        for module in self.by_dotted.get(dotted, []):
            if module.path not in seen:
                seen.add(module.path)
                found.append(module)
        return found

    def _follow_import(
        self, site: Definition, depth: int, seen: frozenset[str]
    ) -> tuple[Definition, str, str] | None:
        """Walk ``from x import y`` chains to the module that finally defines ``y``."""
        if depth > MAX_IMPORT_DEPTH or site.binding_key in seen:
            return None
        if site.source_name is None:
            return None
        candidates = self._modules_for(site.source_module or "")
        if len(candidates) != 1:
            return None
        module = candidates[0]
        target = _effective_site(module.sites(MODULE_SCOPE, site.source_name), 10**9)
        if target is None:
            # ``from pkg import sub``: ``sub`` may be the indexed module ``pkg.sub``.
            submodule = self._submodule(site.source_module or "", site.source_name)
            if submodule is not None and submodule.module_binding is not None:
                return (
                    submodule.module_binding,
                    VERIFIED,
                    f"{site.path}:{site.line} imports the submodule {submodule.path}",
                )
            return None
        if target.kind == "import":
            followed = self._follow_import(target, depth + 1, seen | {site.binding_key})
            if followed is None:
                return None
            resolved, resolution, evidence = followed
            return resolved, resolution, (
                f"{site.path}:{site.line} imports '{site.source_name}' from '{site.source_module}'; {evidence}"
            )
        return target, VERIFIED, (
            f"{site.path}:{site.line} imports '{site.source_name}' from '{site.source_module}' "
            f"-> {target.binding_key} (line {target.line})"
        )