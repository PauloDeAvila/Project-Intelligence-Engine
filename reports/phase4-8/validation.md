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
| 6 — Contexto incremental/cache | PASS_EXTERNAL_CONTROLLED_SINGLE_PAIR | Hashes, compilador, cache persistente e invalidação após mudança cobertos; um par DeepSeek real após reinício passou no oráculo: 237 → 167 tokens. Ainda não é evidência estatística. |
| 7 — Execução local | PASS_LOCAL | Allowlist, limites, replay e timeouts fail-closed cobertos. |
| 8 — Certificação contínua | PARTIAL_NOT_CERTIFIED | GLM v5 e DeepSeek 3.2 tiveram pilotos válidos; o piloto DeepSeek ampliado cobriu 6 tarefas/12 chamadas, 93,226% de redução total e 6/6 em ambos os braços. Ainda faltam Codex, Blender/Web e generalização estatística independente. |

## Alteração desta rodada

MultiAgentMemory.handoff() e ContextRuntime.handoff() transferem um checkpoint
validado para outro agente sem copiar o histórico da tarefa. A proveniência
inclui agente de origem, sequência, `context_version` e hash do checkpoint original.

## Prova externa adicional da Fase 6

O runtime foi fechado e reaberto após a criação do checkpoint. O braço baseline
recebeu o contexto completo; o braço otimizado recebeu somente o checkpoint
restaurado e verificado por SHA-256. Ambos usaram `infinity/deepseek-v3.2`,
retornaram `finish_reason=stop` e passaram o mesmo oráculo.

- Entrada: 193 → 123 tokens, redução de 36,269%.
- Total (entrada + saída): 237 → 167 tokens, redução de 29,536%.
- Evidência: `context-runtime-external-restart-token-proof.json`.
- Escopo: um único par controlado; não substitui a certificação Codex nem prova
  generalização estatística.

## Limitações

O servidor MCP PIE disponível nesta sessão está configurado para outra raiz e
foi deliberadamente excluído da evidência. Os pilotos GLM e DeepSeek reportam
uso real, mas continuam limitados a três tarefas cada e não substituem a
certificação oficial Codex nem a bateria Blender/Web.

O backup e o diff sanitizado da configuração Codex estão em
`reports/phase4-8/routing-preflight-20261116.*`; o servidor original Blender e
`node_repl` não foram modificados.

## Latência p95

O p95 foi calculado a partir das seis latências individuais preservadas no
piloto DeepSeek, com interpolação inclusiva. O baseline teve p95 de 3,76473 s e
o PIE de 2,72131 s, redução descritiva de 27,713%. Com apenas três pares, isso
não é uma estimativa estatística. O valor também mede a chamada ao provedor,
não o p95 de uma consulta local indexada de 100 ms.

Evidência: `phase8-latency-analysis-20261116.json`.

## Piloto DeepSeek ampliado

O mesmo corpus e seed foram executados com seis tarefas pareadas, sem retries.
As doze chamadas reportaram uso real e passaram o oráculo: baseline 52.522
tokens, PIE 3.558 tokens, redução total de 93,226%. Como as três primeiras
tarefas se sobrepõem ao piloto anterior, o resultado amplia a cobertura, mas
não deve ser tratado como seis pares estatisticamente independentes.

Evidência: `deepseek-real-pilot-expanded-20261116.json`.

## Piloto DeepSeek com seed independente

Uma segunda bateria de seis tarefas foi executada com seed `20261117`, mantendo
corpus, modelo, cap de saída, gateway e oráculo. As doze chamadas reportaram uso
real e passaram: baseline 52.735 tokens, PIE 3.543 tokens, redução total de
93,282%; a entrada não cacheada caiu 96,832%. A auditoria posterior dos dois
`audit.json` encontrou interseção zero entre os 12 símbolos, embora a disjunção
não seja uma propriedade imposta pelo runner.

Evidência: `deepseek-real-pilot-independent-20261117.json`.

As duas réplicas DeepSeek apresentaram 93,226% e 93,282% de economia total,
com média de 93,254% e variação de 0,056 ponto percentual, sempre com correção
6/6. A auditoria confirmou 12 símbolos distintos. Isso é consistência
descritiva promissora, mas não certificação estatística completa: ambas usam o
mesmo provider e corpus.

Evidência: `deepseek-replication-analysis-20261117.json`.
