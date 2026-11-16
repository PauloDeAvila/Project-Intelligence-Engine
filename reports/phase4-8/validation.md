# PIE Context Runtime — Fases 4–8

## Veredito

PARTIAL_LOCAL_VALIDATION; certificação externa NOT_CERTIFIED.

## Evidência executada

- Índice local: CURRENT, workspace_match=true, 263 arquivos, 2.212 símbolos e 2.550 imports.
- Testes focados: 74 passed.
- Suíte completa: 710 passed, 4 skipped, 126 subtests passed.
- O handoff codex → deepseek foi exercitado com checkpoint persistente,
  hash de origem e proveniência preservada.

## Estado por fase

| Fase | Estado | Conclusão |
|---|---|---|
| 4 — Consolidação | PASS_LOCAL | Sem regressões locais; persistência após reinício coberta; MCP desta sessão aponta para outra raiz. |
| 5 — Memória entre agentes | PASS_EXTERNAL_CONTROLLED | Handoff real OpenCode/DeepSeek executado após reinício; `context_version` durável e histórico completo não enviado. |
| 6 — Contexto incremental/cache | PASS_LOCAL_RESTART | Hashes, compilador, cache persistente e invalidação após mudança cobertos; falta prova de tokens após reinício do agente. |
| 7 — Execução local | PASS_LOCAL | Allowlist, limites, replay e timeouts fail-closed cobertos. |
| 8 — Certificação contínua | PARTIAL_NOT_CERTIFIED | GLM v5 teve 3/3 em ambos os braços; DeepSeek teve uso real e 93,843% de redução observacional, mas baseline 2/3, portanto sem par de qualidade equivalente. |

## Alteração desta rodada

MultiAgentMemory.handoff() e ContextRuntime.handoff() transferem um checkpoint
validado para outro agente sem copiar o histórico da tarefa. A proveniência
inclui agente de origem, sequência, `context_version` e hash do checkpoint original.

## Limitações

O servidor MCP PIE disponível nesta sessão está configurado para outra raiz e
foi deliberadamente excluído da evidência. O piloto local existente reporta
88,875% de economia total em três tarefas GLM, mas isso não comprova
generalização estatística nem certificação oficial.
