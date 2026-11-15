# Fase 3.15 — instrumentação de correlação por execução

## Implementado

Antes de iniciar `codex exec`, o executor gera deterministically `run_id` e `pair_id`, e define `PIE_RUN_ID`, `PIE_PAIR_ID`, `PIE_TASK_ID`, `PIE_CONDITION`, `PIE_APP` e `PIE_SCENARIO_ID` no ambiente filho.

O gateway herda esses campos e os grava nos eventos lifecycle. O ledger SQLite agora possui `pair_id`, com migração compatível para bases existentes. Imports de uso do provedor incluem `pair_id` no identificador idempotente.

O certificador rejeita registros sem `pair_id` e rejeita braços com `pair_id` divergente.

## Validação offline

- Testes direcionados: `25 passed, 7 subtests`.
- Suíte completa: `539 passed, 5 skipped, 133 subtests`.
- Chamadas reais após a alteração: `0`.
- Nenhum prompt, resposta, credencial ou token de autenticação é persistido.

Esta alteração melhora a evidência de futuras baterias; não promove os 12 registros históricos a certificados. O status permanece `NOT_CERTIFIED`.
