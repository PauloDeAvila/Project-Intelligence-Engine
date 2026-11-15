# Fase 3.16 — aceitação offline do controlador

## Resultado

Decisão: `BLOCKED_WITH_EVIDENCE`.

O controlador único foi implementado em `pie.certification.controller` e exposto como `pie-phase3-controller`. Ele gera um manifesto de 12 sessões, divide a execução em lotes 4+8, impede retries automáticos e não inicia processos Codex no modo de planejamento.

## Gates aprovados

- Suíte completa: `543 passed, 5 skipped, 133 subtests`.
- Manifesto: 6 sessões Blender + 6 Web.
- IDs determinísticos: `run_id` por execução e `pair_id` por cenário.
- Oráculos independentes: propriedades Blender e fixture Web local.
- Configuração persistente: hash preservado `850C2E…8416C`.
- Sessões de modelo nesta etapa: `0`.

## Bloqueios explícitos

O piloto real não foi executado por escopo da etapa. Antes dele ainda é necessário auditar fixtures finais com o controlador, preparar worktrees/overlays do HEAD atual e obter autorização independente para o lote de quatro sessões.

Certificação: `NOT_CERTIFIED`.
