# Fase 3.4 — estratégia de autenticação

## Estratégias avaliadas

| Estratégia | Decisão | Motivo |
|---|---|---|
| A — autenticação independente | não selecionada | exigiria login adicional e intervenção do usuário |
| B — copiar credencial para perfis | rejeitada | expõe segredo em diretórios temporários |
| C — referência controlada à autenticação original | pendente | precisa de validação oficial do Codex nesta instalação; não será presumida |

## Estado escolhido

`BLOCKED_AUTH_STRATEGY_PENDING`.

O ambiente original autentica via conta ChatGPT. O Codex não oferece, nesta instalação, um parâmetro documentado observado no diagnóstico para apontar um `CODEX_HOME` alternativo a uma sessão existente sem compartilhar o material de autenticação. Não foi criada cópia, link ou exportação da credencial.

Para liberar o benchmark, é necessária uma destas opções:

1. autenticação independente oficial em cada perfil; ou
2. confirmação/autorização para uma estratégia de perfil temporário suportada pelo Codex, mantendo `CODEX_HOME` original e aplicando apenas configuração MCP reversível.

Nenhuma chamada de modelo será iniciada enquanto essa decisão não estiver validada.
