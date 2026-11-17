# Auditoria independente OpenCode/DeepSeek — Fases 4–8

Data: 2026-11-16  
Modo: somente leitura; nenhum benchmark pago, edição ou alteração de configuração  
Agente: OpenCode com `infinity/deepseek-v3.2`

## Resultado

| Fase | Estado | Evidência principal | Lacuna principal |
|---|---|---|---|
| 4 — Consolidação | `PASS_LOCAL` | `710 passed, 4 skipped, 126 subtests`; runtime MCP; persistência local; Web E2E do checkout atual | Handshake Blender ao vivo bloqueado; conector MCP do app ainda aponta para outra raiz |
| 5 — Memória entre agentes | `PASS_CONTROLLED` | Handoff real OpenCode/DeepSeek após reinício, com hash e proveniência, sem histórico completo | Apenas um handoff controlado; checkpoint limitado a 16 KB |
| 6 — Contexto/cache incremental | `PARTIAL` | Cache SHA-256, invalidação por mudança e persistência após reinício cobertos por testes | Falta redução de tokens com provedor real após reinício do agente |
| 7 — Execução local | `PASS_LOCAL` | Allowlists, argumentos limitados, replay idempotente, timeouts fail-closed, deltas Blender/Web | Falta métrica isolada de chamadas/tempo de modelo economizados pelo reuso |
| 8 — Certificação contínua | `PARTIAL` | A/B pareado com oráculos e uso real: GLM 88,875%; DeepSeek 3.2 93,801% | Sem certificação Codex, sem bateria Blender/Web completa, somente 3 pares por modelo e sem p95 |

## Arquivos confirmados

- `src/pie/runtime/multi_agent_memory.py`
- `src/pie/retrieval/task_memory.py`
- `src/pie/retrieval/evidence_atoms.py`
- `src/pie/retrieval/context_compiler.py`
- `src/pie/runtime/local_execution.py`
- `src/pie/runtime/replay.py`
- `src/pie/certification/regression.py`
- `src/pie/certification/provider_usage.py`
- `reports/phase4-8/live-agent-handoff.md`
- `reports/phase4-8/deepseek-real-pilot-paired-512.md`
- `reports/phase4-8/validation.md`
- `reports/phase4-8/blender-runtime-diagnostic-20261116.md`

## Conclusão

O parecer independente confirma que a implementação avançou além de uma proposta arquitetural, mas não sustenta `CERTIFIED`. O próximo bloqueio externo é o runtime Blender conectado; a lacuna técnica mais importante restante é provar redução de tokens reais após reinício do agente.
