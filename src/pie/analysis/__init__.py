"""Symbol analysis package: scopes, definitions, references and name resolution."""
from pie.analysis.definitions import Definition, collect_definitions
from pie.analysis.references import Usage, collect_usages
from pie.analysis.resolver import (
    BUILTIN,
    ModuleAnalysis,
    ModuleFacts,
    Reference,
    Resolver,
    analyze_module,
    analyze_source,
)
from pie.analysis.scopes import Scope, build_scopes

__all__ = [
    "BUILTIN",
    "Definition",
    "ModuleAnalysis",
    "ModuleFacts",
    "Reference",
    "Resolver",
    "Scope",
    "Usage",
    "analyze_module",
    "analyze_source",
    "build_scopes",
    "collect_definitions",
    "collect_usages",
]