# PIE Context Runtime — Fases 4–8

## Veredito

PARTIAL_LOCAL_VALIDATION; certificação externa NOT_CERTIFIED.

## Evidência executada

- Índice local: CURRENT, workspace_match=true, 280 arquivos, 2.280 símbolos e 2.646 imports, verificado no head de implementação `11c6d80`.
- Testes focados: 74 passed.
- Suíte completa histórica: 710 passed, 4 skipped, 126 subtests passed.
- Revalidação focada das Fases 5–7: 95 passed, 0 failed; evidência em `acceptance-focus-rerun-20261117.json`.
- Testes focados do gateway Web e do gate: 25 passed em 0,29 s.
- Suíte de regressão mais recente: `uv run pytest -q --basetemp .pytest-tmp-full-web-fix` — 727 passed, 4 skipped, 126 subtests passed em 30,30 s.
- `uv run python tools/verify_context_runtime.py` — `PASS_LOCAL`; o verificador registra `external_provider_usage=unavailable` e não promove evidência sintética a certificação.
- Reexecução persistida em `context-runtime-verifier-final-20261117.json`; os seis pilares passaram localmente, com `NOT_CERTIFIED` mantido.
- Testes de execução local, exposição Web e persistência Delta: 35 passed, 0 failed.
- Checagem Blender ao vivo: processo `blender.exe` PID 18196, endpoint `127.0.0.1:9876`, Blender 5.3.0, addon 2.0, protocolo 16/16; leituras nativa e PIE de status/cena passaram.
- Recuperação Blender: 5 testes focados passaram; o endpoint ativo foi reutilizado sem iniciar duplicata. O preflight Codex agora está conectado à recuperação; o caminho de processo ausente é coberto por teste unitário fail-closed, mas ainda não foi exercitado ao vivo.
- Executor Codex isolado: `CODEX_HOME` temporário com apenas o servidor esperado, esforço `medium` preservado e limpeza automática; a suíte atual tem 727 testes aprovados. Dois pares oficiais Blender e um par Web controlado foram executados por esse caminho.
- Consulta local indexada: 100 amostras, p95 de 3,6046 ms (meta de 100 ms aprovada), sem chamadas de provider.
- Isolamento entre dois workspaces: restauração cruzada retornou `NOT_FOUND`, e
  cada workspace restaurou somente seu próprio checkpoint.
- O handoff codex → deepseek foi exercitado com checkpoint persistente,
  hash de origem e proveniência preservada.
- O handoff oficial Codex → GLM foi executado: o Codex criou uma tarefa e um
  checkpoint via `pie_runtime`, o PIE restaurou o registro e o GLM recebeu
  apenas o checkpoint compilado, sem histórico completo. O oráculo passou.
  Evidência: `codex-glm-official-handoff-20261117.json`.
- A primeira sonda real do Codex confirmou o roteamento para
  `pie-blender-optimized`, sem chamar servidores proibidos. As duas ferramentas
  de leitura falharam porque não havia processo Blender conectado; os tokens
  reportados foram 137.115 de entrada e 1.019 de saída. Evidência:
  `codex-pie-blender-route-probe-20261117.json`.
- A sonda Web real do Codex confirmou o roteamento exclusivo para
  `pie-web-optimized` na fixture local. Navegação, dois snapshots e o clique
  passaram; o título `PIE Phase 3 Fixture` e o marcador `PIE_WEB_FIXTURE_V1`
  foram confirmados. Uso reportado: 226.276 tokens de entrada, 205.440
  cacheados, 797 de saída e 413 de raciocínio. Evidência:
  `codex-pie-web-route-probe-20261117.json`.
- Após o Blender voltar a estar ativo, uma sonda Codex real alcançou o Blender
  5.3.0 pelo `pie-blender-optimized`: addon 2.0, protocolo 16/16 e cena com 3
  objetos. As duas chamadas PIE passaram e nada foi alterado. O Codex também
  acionou automaticamente `cua_repl` para o resumo final; por isso a integração
  está comprovada, mas o isolamento estrito de servidores permanece parcial.
  Evidência: `codex-pie-blender-live-route-probe-20261117.json`.
- Uma sonda com `CODEX_HOME` temporário expôs somente `pie-blender-optimized`;
  as duas ferramentas passaram sem `cua_repl` ou outro servidor. Uso reportado:
  72.491 tokens de entrada, 54.144 cacheados, 500 de saída e 72.991 totais.
  Evidência: `codex-pie-blender-isolated-route-probe-20261117.json`.
- A consulta seletiva `pie_blender_get_object("Cube")` também passou ao vivo e
  retornou nome, tipo, localização e material corretos; a leitura posterior da
  cena confirmou que nada foi alterado. Isso valida o contrato seletivo na cena
  padrão, mas não mede tokens nem substitui a fixture `PIE_Large`.
  Evidência: `blender-live-selective-query-20261117.json`.
- Um par A/B real da cena padrão com DeepSeek 3.2 passou o oráculo em ambos os
  braços: baseline 5.201 tokens, PIE 246 tokens, economia total de 95,27%.
  A entrada caiu 95,897%; a latência foi 2,8839 s contra 2,9077 s. É uma
  réplica única local e permanece `PILOT_VALID_NOT_CERTIFIED`.
  Evidência: `blender-live-default-cube-deepseek-20261117.json`.
- Três pares A/B reais da cena padrão com DeepSeek 3.2 passaram o oráculo em
  ambos os braços (3/3): baseline agregado 15.603 tokens, PIE 738 tokens,
  economia total ponderada de 95,27014%; entrada não cacheada de 5.191 para
  153 tokens (97,052591%). O primeiro par foi cold-cache e os pares 2–3
  reportaram cache nos dois braços; a variação está registrada no gate.
  Evidência: `blender-live-default-cube-deepseek-replication-gate-20261117.json`.
- O preflight de roteamento no checkout atual passou para Web completo e o
  gateway Blender isolado passou initialize, `tools/list`, `get_addon_status` e
  `get_scene_info`; a falha anterior do processo não foi usada como evidência
  final.

## Estado por fase

| Fase | Estado | Conclusão |
|---|---|---|
| 4 — Consolidação | PARTIAL_EXTERNAL_CONTROLLED | Roteamento Codex → PIE e isolamento temporário comprovados nos dois domínios; persistência de eventos e recuperação Blender passaram. |
| 5 — Memória entre agentes | PASS_EXTERNAL_CONTROLLED | Codex oficial criou o checkpoint pelo PIE e o GLM recebeu somente o contexto compilado, sem histórico completo; isolamento entre workspaces passou. |
| 6 — Contexto incremental/cache | PASS_EXTERNAL_CONTROLLED_SINGLE_PAIR | Hashes, compilador, cache persistente e invalidação após mudança cobertos; um par DeepSeek real após reinício passou no oráculo: 237 → 167 tokens. Ainda não é evidência estatística. |
| 7 — Execução local | PASS_LOCAL | Allowlist, limites, replay, timeouts fail-closed e testes de segurança passaram; consulta SQLite local p95 de 3,6046 ms. |
| 8 — Certificação contínua | PARTIAL_NOT_CERTIFIED | Dois pares Codex Blender válidos produziram 44,484% de economia agregada; um par Web controlado produziu −45,469%. A terceira repetição Blender falhou por chamada MCP extra; faltam repetições e generalização. |

O provider atual do OpenCode também foi verificado separadamente: `infinity`
expôs `gambiarraapi/deepseek-v3.2`, que respondeu ao probe real com 55 tokens de
entrada e 6 de saída. Evidência: `opencode-deepseek-connection-20261116.json`.

## Piloto GLM v5

O provider local `gambiarraapi/glm-5.3-flash` também produziu uso real em três
pares da fixture de repositório Rich. Os oráculos passaram em 3/3 nos dois
braços: 17.447 → 1.941 tokens, economia ponderada de 88,875%, com redução de
entrada de 89,196%. O resultado permanece `PILOT_VALID_NOT_CERTIFIED`: é uma
fixture controlada e não certifica o provider oficial Codex.

Evidência: `reports/phase3/context-runtime-verifier-glm-v5.json` e
`reports/phase3/glm-real-pilot-live-v5/summary.json`.

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

## Execução local e latência do índice

A bateria de execução local, exposição de contexto Web e persistência Delta passou
35 testes. A consulta indexada `ContextRuntime` foi repetida 100 vezes em um
processo único: p50 2,8788 ms, p95 3,6046 ms e p99 3,8769 ms. Esse p95 atende à
meta de 100 ms para consultas locais, mas não mede a latência do modelo ou do
MCP. Evidências: `local-query-latency-20261116.json` e o comando registrado em
`validation.json`.

## Limitações

O servidor MCP PIE disponível nesta sessão está configurado para outra raiz e
foi deliberadamente excluído da evidência. Os pilotos GLM e DeepSeek reportam
uso real, mas continuam limitados às fixtures e aos cenários registrados; não
substituem a certificação oficial Codex nem uma generalização ampla para
Blender/Web.

O preflight agora testa a conectividade TCP local do upstream Blender antes de
iniciar o provider. Se `127.0.0.1:9876` (ou o endpoint configurado por
`BLENDER_MCP_HOST`/`BLENDER_MCP_PORT`) não responder, a captura é bloqueada
antes do modelo. A guarda passou nos testes focados e na suíte completa; o
Blender ainda não está ativo neste host para validar o caminho positivo.

O backup e o diff sanitizado da configuração Codex estão em
`reports/phase4-8/routing-preflight-20261116.*`; o servidor original Blender e
`node_repl` não foram modificados.

## Probe Blender ao vivo

O gateway atual foi iniciado contra o checkout correto e encaminhou chamadas ao
addon real do Blender 5.3.0. O addon reportou versão 2.0 e protocolo 16/16;
`tools/list` retornou 15 ferramentas e `get_scene_info` respondeu sem erro.
Usou-se `--factory-startup`, com a cena padrão Cube/Light/Camera, sem alterar a
cena do usuário. A sondagem adicional encontrou `bpy.data.filepath` vazio; a
cena está sem arquivo `.blend` salvo, portanto o hash completo do arquivo
permanece corretamente `null`.

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

## Correção do overhead Web

O gateway Web deixou de anunciar `pie_web_context` por padrão. A compactação
transparente de `browser_snapshot` continua disponível para observações acima
do orçamento; a ferramenta de consulta seletiva só aparece quando explicitamente
exposta. O probe real passou `initialize` e `tools/list`, com 26 ferramentas e
`pie_gateway_output_get` presente.

A fixture atual retornou 415 caracteres, abaixo do orçamento de 2.400, portanto
este gate não reivindica nova economia. Evidência:
`web-transparent-compaction-gate-20261116.json`.

## Fixture Web grande e qualidade do modelo

Na fixture grande, o gateway reduziu o snapshot de 8.632 para 2.164 caracteres
(74,93%) e manteve recuperação. As três tentativas DeepSeek subsequentes,
porém, falharam no oráculo independente; suas diferenças nominais de tokens
foram excluídas. Evidência: `web-large-deepseek-analysis-20261116.json`.

O Evidence Agent separado resolveu a transcrição: o DeepSeek escolheu os campos
`title`, `status` e `marker`, e o código reconstruiu os valores canônicos. O
planejamento caiu de 10.418 para 6.880 tokens (33,96%), com os dois oráculos
aprovados. Esse resultado é `planning_only`; não substitui a certificação da
tarefa completa. Evidência: `web-large-evidence-agent-20261116.json`.

Depois, o runner ponta a ponta passou a deixar o modelo escolher a ação antes
da chamada MCP. Na execução válida, o DeepSeek escolheu o botão, o MCP real
executou quatro chamadas por braço e o código reconstruiu o resultado a partir
de `navigate`, snapshot anterior e snapshot posterior. O consumo caiu de
7.612 para 5.966 tokens (21,624%), com oráculos aprovados nos dois braços.
Tentativas inválidas por limite de saída e perda de título no snapshot
compactado foram preservadas separadamente. Evidência:
`web-large-evidence-task-analysis-20261116.json`.

A tentativa de replicação planejou três pares, mas parou corretamente no R2:
R1 foi válido; R2 emitiu DSML não permitido no braço PIE; R3 não foi iniciado.
Não houve retry e os tokens do R2 foram excluídos. Isso confirma que o caminho
funciona, mas ainda não é reprodutível o bastante para certificação. Evidência:
`web-large-evidence-task-replication-analysis-20261116.json`.

Uma execução intermediária reutilizou a mesma raiz temporária e falhou em dois
testes Delta Store porque o armazenamento global reteve o fingerprint daquela
raiz. Essa execução foi descartada como contaminação de ambiente; a repetição
com raiz nova passou integralmente e é a evidência registrada acima.

Após exigir resposta JSON estruturada no provider, uma nova bateria independente
de três pares passou 3/3. O baseline somou 23.519 tokens e o PIE 18.721, uma
economia ponderada de 20,401%; a faixa entre pares foi de 3,077 pontos
percentuais e os oráculos passaram em todos os braços. Essa é a melhor evidência
reprodutível deste fluxo, mas ainda está limitada a uma fixture e ao provider
local `gambiarraapi/deepseek-v3.2`. Evidência:
`web-large-evidence-task-jsonmode-replication-analysis-20261116.json`.

## Piloto Web Summary

Uma segunda fixture Web determinística foi executada em três pares com o
provider local `gambiarraapi/deepseek-v3.2` e resposta JSON estruturada. Os
oráculos passaram em todos os braços: 3/3 baseline e 3/3 PIE.

- Tokens: 19.965 → 18.001, economia ponderada de 9,837%.
- Entrada: 19.872 → 17.820, redução de 10,326%.
- Saída: 93 → 181, aumento de 94,624%.
- Latência média: 4,1648 s → 2,4789 s.

O ganho total é modesto e a saída aumentou no braço PIE. A diferença de cache
também foi preservada (15.240 → 5.570 tokens), portanto o resultado não deve
ser interpretado como efeito isolado da compactação. Evidência:
`web-summary-evidence-task-replication-analysis-20261116.json`.

## Gate estrito de replicação

O avaliador `pie-certification-replication-v1` foi aplicado a três novos pares
Web Summary com identidade de fixture, índice de replicação, modelo efetivo,
cache observado, rota e trace MCP registrados.

- Gate: `CERTIFIED` para a suíte local.
- Tokens: 20.502 → 17.852, economia ponderada de 12,926%.
- Entrada não cacheada: 4.707 → 2.027, redução de 56,936%.
- Chamadas MCP: 6 por braço.
- Oráculos: 3/3 em ambos os braços.
- Retries: 0; duplicações: 0.

O gate rejeita uso ausente do provider, cache não observado, modelo divergente,
trace MCP incompleto, retry e identidade de replicação repetida. Isso certifica
o protocolo local desta suíte, não o Codex nem o PIE inteiro. Evidência:
`web-summary-replication-gate-20261116.json`.

Também foram executados três pares pós-correção na fixture Web grande: 23.389
→ 18.209 tokens, economia de 22,147% e oráculo 3/3, mas latência média de
3,3924 s → 10,2211 s. A regressão é mantida visível e impede promover esse
caminho como melhoria de desempenho. Evidência:
`web-large-evidence-task-postfix-replication-analysis-20261116.json`.

## Gate estrito de replicação Blender

O Blender 5.3.0 real foi consultado sem edição da cena. O baseline usou o MCP
original; o PIE usou a allowlist `pie_blender_get_object`. O DeepSeek recebeu a
observação de cada braço e o oráculo preservou nomes, coordenadas e materiais.

- Gate local: `CERTIFIED` para a suíte.
- Pares: 3/3 válidos.
- Tokens: 16.126 → 1.044, economia ponderada de 93,526%.
- Entrada não cacheada: 9.622 → 166, redução de 98,275%.
- Oráculos: 3/3 em ambos os braços.
- Chamadas MCP: 3 por braço.
- Retries: 0; duplicações: 0.

As duas primeiras tentativas inválidas foram mantidas: catálogo PIE sem
allowlist causou limite de raciocínio; depois o oráculo foi corrigido para
tratar `mesh`/`MESH` como o mesmo enum MCP, sem normalizar nomes ou valores.
A latência teve alta variabilidade. O hash da fixture representa o oráculo e a
identidade verificada da cena. Um snapshot canônico independente registrou 64
objetos mesh, SHA-256 `7de1f682...e6df1c` e nenhuma alteração na cena; ele ainda
não é um hash de arquivo `.blend` completo. Evidências:
`blender-live-replication-gate-20261116.json` e
`blender-live-scene-snapshot-20261116.json`.

## Segundo cenário Blender

O runner foi ampliado para uma segunda tarefa determinística, `PIE_Large_Cube_63`,
validada diretamente no Blender antes do A/B e repetida três vezes.

- Tokens agregados: 15.979 → 837.
- Economia ponderada: 94,762%.
- Entrada não cacheada: 10.183 → 184, economia de 98,193%.
- Oráculos: 3/3 em ambos os braços.
- Chamadas MCP: 3 por braço.
- Retries: 0; modelo efetivo `gambiarraapi/deepseek-v3.2`.
- Latência média: 3,4557 s → 1,8092 s.
- Gate: `CERTIFIED` para a suíte local de três pares.

Esse cenário amplia a cobertura de objetos, mas continua restrito à fixture
Blender local e ao provider DeepSeek configurado. Não estabelece certificação
oficial do Codex nem generalização para outras tarefas. Evidência:
`blender-object63-replication-gate-20261116.json`.

## Atualização: A/B oficial Codex pelo executor isolado

Em 2026-11-17, o executor isolado foi usado com `gpt-5.6-luna`, esforço
`medium`, `CODEX_HOME` temporário e worktrees limpos.

### Blender

Dois pares válidos do cenário `Cube` passaram o oráculo independente e a rota:

- Baseline: `blender` → `get_addon_status`, `get_scene_info`.
- Optimized: `pie-blender-optimized` → `get_addon_status`,
  `pie_blender_get_object`.
- Agregado válido: `239.237` → `132.814` tokens, economia de `44,484%`.
- Input não cacheado: `33.866` → `14.752`, economia de `56,440%`.
- Latência média: optimized `9,165%` mais lenta.

A repetição Blender R3 foi preservada como inválida porque o baseline chamou
`get_scene_info` duas vezes. O braço optimized não foi iniciado e não houve
retry automático. Evidências:
`codex-blender-default-aggregate-20261117.json`,
`codex-blender-default-r2-20261117.json` e
`codex-blender-default-r3-invalid-20261117.json`.

### Web

Um par Web controlado passou o oráculo da fixture local e executou quatro
chamadas em cada braço: navegação, snapshot, clique e snapshot.

- Baseline: `63.601` tokens.
- Optimized: `92.520` tokens.
- Resultado: **−45,469% de economia** (regressão).
- Latência praticamente estável, com optimized `0,023%` mais lento.
- Nenhuma página externa foi acessada.

O baseline criou apenas logs `.playwright-mcp`; eles foram removidos no
worktree temporário e o checkout foi confirmado limpo antes do optimized.
Evidência: `codex-web-local-controlled-pair-20261117.json`.

Esses resultados são uso reportado pelo Codex e não estimativas por caracteres.
Ainda assim, a certificação geral permanece `NOT_CERTIFIED`: falta completar a
amostra de três pares por domínio e investigar a chamada Blender duplicada.
