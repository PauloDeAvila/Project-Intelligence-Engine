# PIE Fase 3.4 — diagnóstico definitivo de autenticação e pré-voo

## Veredito

`BLOCKED`.

O Codex original está autenticado localmente (`AUTH_VALIDATED_LOCAL`), mas os perfis isolados baseline e optimized não têm autenticação disponível (`AUTH_MISSING`). O pré-voo agora identifica o problema antes de qualquer chamada de modelo.

## Causa raiz

Os `CODEX_HOME` temporários receberam apenas `config.toml`. A autenticação original é de conta ChatGPT e não foi copiada por segurança. A primeira captura anterior falhou com `RuntimeError` antes de gerar `turn.completed.usage`.

## Correções implementadas

- Novo comando `pie-live preflight`.
- `capture` executa pré-voo obrigatório antes do `codex exec`.
- Verificação sanitizada de `codex login status`.
- Detecção de `AUTH_MISSING`, `AUTH_INVALID` e `AUTH_UNAVAILABLE`.
- Validação de modelo, worktree, configuração, servidor MCP e diretório de evidências.
- Nenhum segredo é impresso ou exportado.

## Validação

- Suíte: `531 passed, 5 skipped, 133 subtests passed`.
- Pré-voo original: autenticação local PASS.
- Pré-voo baseline: configuração/MCP/worktree PASS; autenticação BLOCKED.
- Pré-voo optimized: configuração/MCP/worktree PASS; autenticação BLOCKED.
- Chamadas de modelo nesta fase: `0`.

## Próximo passo

Selecionar uma estratégia de autenticação oficialmente suportada: login independente nos perfis ou uso controlado do `CODEX_HOME` original com configuração MCP reversível. Essa decisão requer nova autorização antes de qualquer chamada que consuma quota.
