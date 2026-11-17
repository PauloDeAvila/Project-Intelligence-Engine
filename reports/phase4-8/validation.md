# PIE Context Runtime — Fases 4–8

## Veredito

PARTIAL_LOCAL_VALIDATION; certificação externa NOT_CERTIFIED.

## Evidência executada

- Índice local: CURRENT, workspace_match=true, 263 arquivos, 2.212 símbolos e 2.550 imports.
- Testes focados: 74 passed.
- Suíte completa: 710 passed, 4 skipped, 126 subtests passed.
- O handoff codex → deepseek foi exercitado com checkpoint persistente,
  hash de origem e proveniência preservada.
- O preflight de roteamento no checkout atual passou para Web completo e o
  gateway Blender isolado passou initialize, `tools/list`, `get_addon_status` e
  `get_scene_info`; a falha anterior do processo não foi usada como evidência
  final.

## Estado por fase

| Fase | Estado | Conclusão |
|---|---|---|
| 4 — Consolidação | PASS_EXTERNAL_CONTROLLED_READ_ONLY | Sem regressões locais; Web E2E e Blender 5.3 real passaram initialize, tools/list, get_addon_status e get_scene_info via PIE. A fixture Blender grande ainda não foi carregada. |
| 5 — Memória entre agentes | PASS_EXTERNAL_CONTROLLED | Handoff real OpenCode/DeepSeek executado após reinício; `context_version` durável e histórico completo não enviado. |
| 6 — Contexto incremental/cache | PASS_EXTERNAL_CONTROLLED_SINGLE_PAIR | Hashes, compilador, cache persistente e invalidação após mudança cobertos; um par DeepSeek real após reinício passou no oráculo: 237 → 167 tokens. Ainda não é evidência estatística. |
| 7 — Execução local | PASS_LOCAL | Allowlist, limites, replay e timeouts fail-closed cobertos. |
| 8 — Certificação contínua | PARTIAL_NOT_CERTIFIED | GLM v5, DeepSeek 3.2, Blender e Web tiveram pilotos locais; Blender mediu 82,934%, mas Web teve −29,098% de economia total apesar de 3/3 oráculos. Ainda faltam certificação Codex e generalização ampla. |

O provider atual do OpenCode também foi verificado separadamente: `infinity`
expôs `gambiarraapi/deepseek-v3.2`, que respondeu ao probe real com 55 tokens de
entrada e 6 de saída. Evidência: `opencode-deepseek-connection-20261116.json`.

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
uso real, mas continuam limitados às fixtures e aos cenários registrados; não
substituem a certificação oficial Codex nem uma generalização ampla para
Blender/Web.

O backup e o diff sanitizado da configuração Codex estão em
`reports/phase4-8/routing-preflight-20261116.*`; o servidor original Blender e
`node_repl` não foram modificados.

## Probe Blender ao vivo

O gateway atual foi iniciado contra o checkout correto e encaminhou chamadas ao
addon real do Blender 5.3.0. O addon reportou versão 2.0 e protocolo 16/16;
`tools/list` retornou 15 ferramentas e `get_scene_info` respondeu sem erro.
Usou-se `--factory-startup`, com a cena padrão Cube/Light/Camera, sem alterar a
cena do usuário.

Evidência: `live-blender-gateway-probe-20261116.json`.

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

## Piloto A/B Blender com DeepSeek

Na sessão Blender isolada, a fixture foi gerada com 64 objetos e 16 materiais e
validada por consulta real. O baseline usou `get_scene_info`; o PIE usou
`pie_blender_get_object` para o mesmo objeto e tarefa. Os três pares passaram o
oráculo. O total caiu de 2.918 para 498 tokens, redução de 82,934%; a latência
mediana, entretanto, aumentou 32,189% (2,4605 s → 3,2525 s).

Esta é uma comparação de capacidade seletiva com contrato próprio, não uma
prova de compactação transparente da mesma ferramenta. A especificação da
fixture veio de outro worktree e seu SHA-256 está registrado; ela não foi
tratada como código do checkout atual.

Evidência: `blender-deepseek-ab-pilot-20261116.json`.

## Piloto A/B Web com DeepSeek

Após corrigir o contrato MCP do clique (`target`, não `ref`), o piloto Web válido
passou 3/3 no oráculo em ambos os braços. O input caiu de 627 para 563 tokens,
mas a saída aumentou de 105 para 382; o total subiu de 732 para 945 tokens,
resultando em **−29,098% de economia**. A latência mediana também piorou de
1,8233 s para 3,1625 s.

Esse resultado negativo permanece visível e impede promover a compactação Web
como economia comprovada. A tentativa anterior com clique inválido está
preservada separadamente como falha do harness.

Evidência: `web-deepseek-ab-pilot-20261116.json` e
`web-deepseek-ab-pilot-20261116-invalid-click.json`.
