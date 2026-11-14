# PIE Fase 3.4 — diagnóstico definitivo de autenticação e pré-voo

## Veredito

`BLOCKED`.

O Codex original está autenticado remotamente (`AUTH_REMOTE_VALIDATED`) após uma única chamada diagnóstica mínima. Os perfis isolados baseline e optimized não têm autenticação disponível (`AUTH_MISSING`). O pré-voo identifica o problema antes de qualquer chamada de benchmark.

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

- Suíte: `532 passed, 5 skipped, 133 subtests passed`.
- Pré-voo original: autenticação local PASS.
- Pré-voo baseline: configuração/MCP/worktree PASS; autenticação BLOCKED.
- Pré-voo optimized: configuração/MCP/worktree PASS; autenticação BLOCKED.
- Chamadas diagnósticas nesta fase: `1`, sem MCP, sem retry.
- Tokens diagnósticos: 19.935 entrada, 0 cache, 10 saída.

## Próximo passo

Selecionar uma estratégia de autenticação oficialmente suportada: login independente nos perfis ou uso controlado do `CODEX_HOME` original com configuração MCP reversível. A chamada diagnóstica não libera a bateria A/B; qualquer nova chamada consumidora de quota requer autorização.
