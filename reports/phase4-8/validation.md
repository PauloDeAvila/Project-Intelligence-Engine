# PIE Context Runtime — Fases 4–8

## Veredito

PARTIAL_LOCAL_VALIDATION; certificação externa NOT_CERTIFIED.

## Evidência executada

- Índice local: CURRENT, workspace_match=true, 263 arquivos, 2.212 símbolos e 2.550 imports.
- Testes focados: 74 passed.
- Suíte completa: 710 passed, 4 skipped, 126 subtests passed.
- O handoff codex → deepseek foi exercitado com checkpoint persistente,
  hash de origem e proveniência preservada.
- O preflight de roteamento no checkout atual passou para Web completo e
  `tools/list` Blender; o upstream Blender ainda falha no handshake.

## Estado por fase

| Fase | Estado | Conclusão |
|---|---|---|
| 4 — Consolidação | PASS_LOCAL | Sem regressões locais; persistência após reinício coberta; MCP desta sessão aponta para outra raiz. |
| 5 — Memória entre agentes | PASS_EXTERNAL_CONTROLLED | Handoff real OpenCode/DeepSeek executado após reinício; `context_version` durável e histórico completo não enviado. |
| 6 — Contexto incremental/cache | PASS_LOCAL_RESTART | Hashes, compilador, cache persistente e invalidação após mudança cobertos; falta prova de tokens após reinício do agente. |
| 7 — Execução local | PASS_LOCAL | Allowlist, limites, replay e timeouts fail-closed cobertos. |
| 8 — Certificação contínua | PARTIAL_NOT_CERTIFIED | GLM v5 e DeepSeek 3.2 tiveram pilotos válidos de 3 pares; DeepSeek mediu 93,801% de redução total e 3/3 em ambos os braços. Ainda faltam Codex, Blender/Web e generalização estatística. |

## Alteração desta rodada

MultiAgentMemory.handoff() e ContextRuntime.handoff() transferem um checkpoint
validado para outro agente sem copiar o histórico da tarefa. A proveniência
inclui agente de origem, sequência, `context_version` e hash do checkpoint original.

## Limitações

O servidor MCP PIE disponível nesta sessão está configurado para outra raiz e
foi deliberadamente excluído da evidência. Os pilotos GLM e DeepSeek reportam
uso real, mas continuam limitados a três tarefas cada e não substituem a
certificação oficial Codex nem a bateria Blender/Web.

O backup e o diff sanitizado da configuração Codex estão em
`reports/phase4-8/routing-preflight-20261116.*`; o servidor original Blender e
`node_repl` não foram modificados.
