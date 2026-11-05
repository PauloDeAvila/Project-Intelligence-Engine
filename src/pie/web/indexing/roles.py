"""Small deterministic semantic-role vocabulary for local search."""

from __future__ import annotations

from ..contracts import WebStateError
from .extractor import tokenize


_ROLE_ALIASES = {
    "search": frozenset({"search", "buscar", "busca", "pesquisa", "pesquisar", "consulta"}),
    "login": frozenset({"login", "signin", "entrar", "acesso", "autenticar"}),
    "submit": frozenset({"submit", "enviar", "salvar", "save", "confirmar", "confirm"}),
    "navigation": frozenset({"navigation", "navegacao", "navegação", "menu", "nav"}),
    "results": frozenset({"results", "resultado", "resultados", "table", "tabela", "grid"}),
    "dialog": frozenset({"dialog", "modal", "janela"}),
    "link": frozenset({"link", "enlace", "url"}),
}
_ROLE_TARGETS = {
    "search": frozenset({"input", "textarea", "combobox"}),
    "login": frozenset({"form", "input", "button"}),
    "submit": frozenset({"button"}),
    "navigation": frozenset({"navigation", "menu", "link"}),
    "results": frozenset({"table", "grid", "row", "cell"}),
    "dialog": frozenset({"dialog"}),
    "link": frozenset({"link"}),
}


class SemanticRoleMatcher:
    """Map literal natural-language hints to a closed semantic role set."""

    def infer(self, query: str) -> tuple[str, ...]:
        terms = set(tokenize(query))
        roles = [role for role, aliases in _ROLE_ALIASES.items() if terms.intersection(aliases)]
        return tuple(roles)

    def targets_for(self, semantic_role: str) -> frozenset[str]:
        if not isinstance(semantic_role, str) or len(semantic_role) > 64:
            raise WebStateError("semantic_role is outside the safe bound")
        try:
            return _ROLE_TARGETS[semantic_role.casefold()]
        except KeyError as exc:
            raise WebStateError("semantic_role is not supported") from exc

    def matches(self, query: str, actual_role: str) -> tuple[str, ...]:
        if not isinstance(actual_role, str):
            raise WebStateError("actual_role must be text")
        return tuple(role for role in self.infer(query) if actual_role.casefold() in _ROLE_TARGETS[role])


__all__ = ["SemanticRoleMatcher"]
