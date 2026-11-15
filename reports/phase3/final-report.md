# PIE Fase 3 — certificação real e monitoramento

## Veredito

**NOT_CERTIFIED — roteamento Blender validado, economia A/B ainda não certificada.** A baseline corrigida e uma nova sessão optimized passaram uso do provedor, ferramentas esperadas, oráculos e correlação lifecycle exata. Porém, este é apenas um par válido e o resultado optimized aumentou os tokens totais.

## Baseline Blender v2 — diagnóstico do oráculo

A execução `94-blender-v2-baseline.json` confirmou a rota correta (`blender/get_scene_info`, uma chamada) e uso real do provedor: 45.355 tokens de entrada, 39.680 cacheados, 489 de saída e 15.598,589 ms. Ela não foi promovida a par porque o oráculo comparava `object_type="MESH"` enquanto o texto do MCP original retornou `object_type="mesh"`; nome, localização, materiais, chaves e tipos estavam corretos. O braço optimized não foi iniciado e não houve retry.

A avaliação foi corrigida para normalizar somente esse enum de representação, preservando comparação exata dos demais campos. A evidência detalhada está em [`94-blender-v2-baseline.md`](94-blender-v2-baseline.md). Essa correção ainda precisa ser exercitada em uma nova sessão autorizada antes de qualquer A/B; a certificação permanece `NOT_CERTIFIED`.

## Baseline Blender v2 — incidente de upstream

A tentativa seguinte foi roteada corretamente e consumiu 45.399 tokens de entrada, 39.680 cacheados, 814 de saída e 22.659,152 ms. O oráculo encontrou `object_name` e `object_type` nulos e arrays vazios. A investigação mostrou que o perfil temporário omitiu a porta Blender `9877`, usada pelo perfil previamente validado. O braço optimized não foi executado e não houve retry. Evidência: [`96-blender-v2-fixed-baseline.md`](96-blender-v2-fixed-baseline.md). O próximo gate é sem modelo, com a porta explícita; a certificação continua `NOT_CERTIFIED`.

## Primeiro par Blender v3 válido — 2026-11-15

O cenário v3 corrigiu a capacidade baseline: `get_scene_info` não expunha `material_names` na resposta real, então o baseline passou a usar uma única chamada read-only a `execute_blender_code`; o optimized usou `pie_blender_query_scene`. O gate sem modelo confirmou a fixture real em ambos os braços.

| Condição | Input | Cache | Não cacheado | Output | Total | Latência | MCP | Oráculo | Rota |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| Baseline | 44.726 | 39.040 | 5.686 | 593 | 45.319 | 18.378,347 ms | 1 | PASS | VALID |
| Optimized | 44.554 | 39.040 | 5.514 | 321 | 44.875 | 13.446,835 ms | 1 | PASS | VALID |

Economia de input: **0,385%**; de input não cacheado: **3,024%**; total: **0,980%**. Latência caiu 4.931,512 ms. O resultado é positivo, porém é apenas um par e não certifica o domínio. Evidência: [`101-blender-v3-pair.md`](101-blender-v3-pair.md).

## Limite de quota desta autorização

O ledger atual registra 20 chamadas autorizadas e 20 sessões Codex concluídas após os incidentes e o par v3. Nenhuma sessão adicional foi iniciada. Blender tem 1 par v3 válido; Web e os pares adicionais necessários para certificação permanecem pendentes. O veredito continua `NOT_CERTIFIED`.

## Web v2 — bloqueio de dependência

A fixture local respondeu em `127.0.0.1:8766`, mas o ambiente tem Node `v24.22.1` sem `npm` e `npx`. O upstream fixado `@playwright/mcp` não foi iniciado e nenhum benchmark Web consumiu quota. Evidência: [`102-web-v2-preparation-blocked.md`](102-web-v2-preparation-blocked.md). O bloqueio requer fornecer npm/npx ou instalar o componente autorizado antes do gate sem modelo.

Os números A/B históricos abaixo são mantidos como evidência preliminar e não devem ser confundidos com o piloto atual. Eles não promovem a certificação porque não satisfazem a cobertura causal e de correlação exigida.

O par usou o mesmo modelo, esforço, prompt, commit e estado inicial. A baseline foi válida; a optimized tem uso real e oráculo textual/Blender aprovados, mas route evidence `INSUFFICIENT_EVIDENCE`. Não houve execução Web nesta etapa nem retry automático.

O par corrigido posterior passou route evidence. A tentativa anterior permanece preservada como
`INSUFFICIENT_EVIDENCE` e não foi promovida nem usada nos cálculos.

## Par Blender corrigido — 2026-11-15

| Condição | Input | Cache | Uncached | Output | Total | Latência | MCP | Oráculo | Rota |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| Baseline | 58,889 | 35,840 | 23,049 | 685 | 59,574 | 17,451.210 ms | 2 | PASS | VALID |
| Optimized | 76,792 | 62,336 | 14,456 | 855 | 77,647 | 22,418.533 ms | 2 | PASS | INSUFFICIENT_EVIDENCE |

Economia input: **-30.401263%**. Economia de input não armazenado em cache: **37.281443%**. Economia total: **-30.337060%**. Latência: **+4,967.323 ms (+28.464061%)**. A redução de contexto não compensou o aumento de tokens totais neste par. Custos permanecem `null`, sem tarifa verificável.

Evidências: [`63-single-optimized-blender.md`](63-single-optimized-blender.md), [`64-blender-single-pair-comparison.json`](64-blender-single-pair-comparison.json) e o diretório forense registrado no primeiro arquivo. O `mcp-tool-events.jsonl` prova o servidor e as ferramentas observadas pelo Codex; a ausência de evento lifecycle exato impede certificação causal do gateway.

## Correção offline da correlação de runtime

Foi corrigida a causa provável da ausência de lifecycle: a captura agora materializa um perfil
Codex efêmero por execução e declara explicitamente no servidor MCP os IDs da execução e o
caminho de telemetria. A correção foi validada sem iniciar modelo ou consumir quota. Evidência:
[`65-runtime-profile-correlation-fix.md`](65-runtime-profile-correlation-fix.md) e
[`65-runtime-profile-correlation-fix.json`](65-runtime-profile-correlation-fix.json).

Ainda falta uma nova sonda real para provar a correlação no gateway. A execução otimizada
anterior foi seguida por uma sonda corrigida, que passou a correlação exata. Evidência:
[`66-single-optimized-blender-correlation.md`](66-single-optimized-blender-correlation.md) e
[`66-blender-pair-certified-routing.json`](66-blender-pair-certified-routing.json).

## Par Blender com roteamento certificado

| Condição | Input | Cache | Uncached | Output | Total | Latência | MCP | Oráculo | Rota |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| Baseline | 58,889 | 35,840 | 23,049 | 685 | 59,574 | 17,451.210 ms | 2 | PASS | VALID |
| Optimized | 111,291 | 94,336 | 16,955 | 758 | 112,049 | 20,743.830 ms | 2 | PASS | VALID |

Economia input: **-88.984360%**. Economia de input não armazenado em cache: **26.439325%**.
Economia total: **-88.083728%**. Latência: **+3,292.620 ms (+18.867574%)**.
O PIE reduziu o input não-cacheado, mas aumentou o custo total reportado pelo provedor neste
par. Isso é um resultado desfavorável válido e não deve ser descartado.

Auditoria independente do registro otimizado: [`66-route-audit.json`](66-route-audit.json),
resultado `EVIDENCE_CERTIFIED`.

## Par Web com roteamento certificado

| Condição | Input | Cache | Uncached | Output | Total | Latência | MCP | Oráculo | Rota |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| Baseline | 66,027 | 56,704 | 9,323 | 305 | 66,332 | 11,878.006 ms | 2 | PASS | VALID |
| Optimized | 66,475 | 56,832 | 9,643 | 300 | 66,775 | 11,681.315 ms | 2 | PASS | VALID |

Economia input: **-0.678510%**. Economia de input não armazenado em cache:
**-3.432372%**. Economia total: **-0.667853%**. Latência: **-196.691 ms (-1.655926%)**.
O par Web é válido, mas não demonstra economia de tokens.
Evidência: [`69-web-pair-comparison.md`](69-web-pair-comparison.md) e
[`69-web-pair-comparison.json`](69-web-pair-comparison.json).
Auditoria independente da rota optimized: [`70-web-route-audit.json`](70-web-route-audit.json),
resultado `EVIDENCE_CERTIFIED`.

## Diagnóstico diferencial da regressão

A análise offline dos dois pares válidos não encontrou chamadas MCP adicionais: ambos fizeram
2 chamadas em cada condição. Também não encontrou aumento relevante de reasoning: Blender
`209 → 211` e Web `151 → 119`.

O gateway optimized registrou `PASSTHROUGH` em todas as respostas observadas. Blender devolveu
359 caracteres, exatamente os 359 recebidos; Web devolveu 824, exatamente os 824 recebidos.
Logo, a compactação não foi acionada e não houve recuperação de conteúdo.

O Blender teve `+52.402` tokens de input e `+52.475` tokens totais, principalmente por aumento
de input cacheado (`35.840 → 94.336`). A Web teve uma regressão pequena de `+443` tokens totais,
com `+320` tokens não-cacheados. A hipótese principal para Blender é overhead de contexto/schema
optimized, mas a decomposição exata em tokens do provedor ainda não está disponível.

Evidência completa: [`71-differential-regression-analysis.md`](71-differential-regression-analysis.md)
e [`71-differential-regression-analysis.json`](71-differential-regression-analysis.json).

## Medição estrutural e correção offline

O diff direto de `tools/list` confirmou overhead estrutural: Blender `18.750 → 20.045`
caracteres e Web `21.177 → 21.583`, com ferramentas adicionais de recuperação/expansão.
Evidência: [`72-structural-overhead-diff.md`](72-structural-overhead-diff.md).

Foi implementada uma exposição seletiva opt-in por tarefa. Nos probes offline, o perfil seletivo
reduziu as listas para 3.792 caracteres no Blender e 1.738 na Web, mantendo explicitamente a
recuperação necessária. Chamadas a ferramentas ocultas falham fechadas e não são encaminhadas.
O comportamento padrão do gateway não mudou. Evidência:
[`73-selective-exposure-diff.md`](73-selective-exposure-diff.md).

## Aceitação offline de compactação

O gate offline foi concluído como `COMPACTION_READY_FOR_AB`, sem iniciar modelo e sem consumir quota. O teste Blender confirmou compactação parcial de uma observação grande sem alterar o resultado de escrita; o teste Web confirmou preservação de referências, recuperação do snapshot sanitizado por `output_id` e igualdade SHA-256; os marcadores confirmaram ausência de chamadas upstream duplicadas. A exposição seletiva também bloqueou chamadas de ferramentas ocultas antes do encaminhamento.

Evidência detalhada: [`74-offline-compaction-acceptance.md`](74-offline-compaction-acceptance.md) e [`74-offline-compaction-acceptance.json`](74-offline-compaction-acceptance.json). Esses resultados são de segurança/recuperação offline e não equivalem a tokens do provedor.

O gate adicional de fixture Blender real passou: uma cena descartável foi gerada pelo Blender 5.3 a partir de `large_scene_spec.json`, com 64 objetos e 16 materiais. A observação de 14.543 caracteres foi reduzida para 3.806 (`PARTIAL`) e teve o digest validado. Evidência: [`75-blender-real-fixture-gate.md`](75-blender-real-fixture-gate.md).

O piloto pago seguinte foi interrompido antes do dispatch MCP. A sessão optimized reportou uso real (`230.071` input, `178.176` cacheados, `1.528` output), mas os servidores `pie-blender-optimized` e `pie-web-optimized` falharam ao iniciar com Windows `os error 3`; foram observados `0` eventos `mcp_tool_call`. Baseline não foi executado e não houve retry. Evidência: [`76-blender-pilot-blocked.md`](76-blender-pilot-blocked.md). Isso não é resultado A/B nem evidência de economia.

Após o diagnóstico, o preflight passou a validar a existência do executável `command` de cada servidor MCP antes de iniciar o Codex. A suíte regressiva atual tem 570 testes aprovados e 5 ignorados.

A correção estrutural foi validada offline nos quatro perfis de domínio: os executáveis são estáveis, o código PIE resolve para o commit experimental correto, os perfis não carregam o domínio oposto e initialize/tools/list/tools/call passam sem modelo. O Web optimized produziu `PARTIAL` no snapshot real (8.965 → 1.003 caracteres); o Blender real retornou `structuredContent`, condição na qual a compactação atual permanece intencionalmente desativada. A suíte final tem 571 testes aprovados e 5 ignorados. Evidência: [`77-offline-environment-gates.md`](77-offline-environment-gates.md).

## A/B estrito (repetições 2 e 3)

| Domínio | Pares | Input B/O | Cache B/O | Output B/O | Total B/O | Economia total | Latência média B/O | MCP B/O |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Blender | 2/3 exigidos | 226951 / 196052 | 186752 / 156416 | 1426 / 1201 | 228377 / 197253 | **13.628343%** | 19641.010 / 17135.516 ms | 4 / 5 |
| Web | 2/3 exigidos | 355463 / 399269 | 318720 / 356992 | 1333 / 1672 | 356796 / 400941 | **-12.372616%** | 21267.743 / 23727.808 ms | 8 / 8 |

Valores `B/O` são baseline/optimized. A economia de input não armazenado em cache foi 1.400532% no Blender e **-15.061372%** na Web. Não houve conversão de caracteres em tokens.

## Evidências e cobertura

- 12 chamadas Codex completadas; 0 retries; modelo `gpt-5.6-luna`, esforço `medium`.
- 8 chamadas tinham aliases e hashes de prompt comuns: 2 pares Blender e 2 Web. Os quatro pilotos iniciais foram health checks, mas tiveram hashes de prompt diferentes e não foram usados na certificação.
- Todos os quatro pares estritos passaram o oráculo; isso demonstra correção nesses casos, não suficiência estatística.
- O SQLite PIE consultado em `C:\Users\phsra\.pie-global\projects\776668a48707658ebd7e41c78fc7d720\index.sqlite3` contém 2 observações reais do gateway Web (`browser_snapshot`, `task_id=unassigned`, `PASSTHROUGH`) e 12 imports de uso Codex validados: 3 baseline/3 optimized por domínio. Os imports têm `source_event_id` determinístico e são idempotentes; eles não provam, sozinhos, o roteamento de cada chamada pelo gateway.
- A configuração preserva `blender`, `node_repl` e os demais servidores; as rotas PIE são opt-in, com 2 de 5 servidores ativos envolvidos.

## Testes

`pytest`: **546 passed, 5 skipped, 133 subtests** (via `uv run --with pytest python -m pytest -q`). A execução sem o caso HTTP intermitente conhecido passou anteriormente com **537 passed, 5 skipped, 1 deselected, 133 subtests**. `compileall`: passou. O preflight agora bloqueia overlays com workspace divergente e manifestos cujo hash não corresponde ao cenário carregado. O status local do checkout retornou `CURRENT`, com `workspace_match=true` e `index_root` igual a `workspace_root`. O servidor PIE MCP disponível nesta sessão continua reportando outra raiz (`C:\\Users\\phsra\\Documents\\Codex\\2026-11-14\\contrato-de-uso-ativo-do-project`), portanto não foi tratado como evidência deste checkout. Evidência adicional: `50-offline-controller-acceptance.json`.

A revalidação da configuração confirmou `pie-blender-optimized` e `pie-web-optimized` no checkout correto, preservando `blender` e `node_repl`. O detalhe sanitizado e o hash do arquivo estão em `43-routing-state-revalidation.json`. A auditoria SQLite posterior confirmou 3 imports baseline e 3 optimized por domínio, mas apenas 2 pares estritamente comparáveis por domínio; a distinção está em `44-telemetry-count-audit.json`.

O cruzamento dos 12 imports com os cinco lifecycle JSONL recuperáveis encontrou zero correspondências por `run_id`; os tokens históricos não podem ser atribuídos individualmente às rotas PIE. Evidência: `45-route-coverage-crosscheck.json`.

O preflight do HEAD `75560b5` passou nos quatro braços em worktree limpo (`46-current-head-preflight.json`), sem iniciar modelo ou consumir quota. O overlay optimized usado para alinhar o `--workspace` foi temporário e não alterou o `config.toml` persistente.

O contrato de correlação foi ampliado com `pair_id` e propagação de contexto no ambiente do Codex e nos eventos lifecycle (`47-run-correlation-instrumentation.json`). A suíte completa após a mudança passou com `539 passed, 5 skipped, 133 subtests`; nenhuma nova sessão real foi executada.

A matriz individual das 12 execuções históricas classificou `0 VALID`, `0 INVALID` e `12 INSUFFICIENT_EVIDENCE`; nenhum registro foi promovido artificialmente. Evidência: `48-historical-traceability.json`.

O controlador offline, o manifesto 4+8 e os cenários com oráculos independentes estão documentados em `49-controller-plan.json` e `50-offline-controller-acceptance.json`. A decisão desta etapa é `BLOCKED_WITH_EVIDENCE`; nenhum modelo foi iniciado.

O piloto autorizado foi iniciado pelo controlador, mas abortado na primeira sessão Blender baseline após uma chamada `execute_blender_code` falhar. Foram consumidas `1/4` sessões; não houve retry nem execução Web. Evidência: `52-pilot-failure.json`. A certificação permanece `NOT_CERTIFIED`.

A auditoria de recuperação em [`56-failure-recovery-audit.md`](56-failure-recovery-audit.md) classificou a primeira falha como `TOOL_RESULT_FAILURE`, mas marcou a causa raiz como `INCONCLUSIVE`: o Codex JSONL, stderr interno, respostas MCP, lifecycle e uso SQLite dessa execução não foram persistidos pelo executor original.

O commit `ecd3158` passou a preservar uso agregado e metadados sanitizados quando uma execução inválida já produziu `turn.completed`; isso melhora a observabilidade sem promover a execução a evidência certificada.

## Diagnóstico Codex/MCP

A chamada diagnóstica inicial falhou no parsing do override transitório `-c`. A tentativa corrigida usando `tools/run_codex_mcp_diagnostic.ps1` iniciou uma sessão real, selecionou `pie-blender-optimized` e reportou tokens (`136207` input, `115968` cache, `691` output), mas `get_addon_status` e `get_scene_info` falharam. Nenhum lifecycle JSONL foi produzido; o ponto interno da falha permanece inconclusivo. Resultado detalhado: `22-codex-mcp-probe-result.json`. Não há certificação nem nova tentativa automática.

Na Fase 3.7, o gateway foi validado offline com as duas ferramentas reais. O bootstrap passou a registrar em `.pie-live-store/mcp-lifecycle.jsonl` mesmo sem variável de ambiente herdada. Também foi corrigido o encerramento do Blender bridge para aguardar saída natural do upstream. Na Fase 3.8, dois gateways Codex chegaram a import, initialize e tools/list, mas nenhum recebeu tools/call; os três erros do Codex confirmam `MCP tool call requires approval, but approval policy is never`. O gate técnico voltou a `READY_FOR_CODEX_PROBE=false` até preparar uma mudança de aprovação explicitamente autorizada.

A Fase 3.10 confirmou que a versão instalada aceita políticas de aprovação temporárias e oferece `--approve-for-me` para `codex exec`. A sonda Fase 3.11 tentou `on-request` + `--approve-for-me`, mas o próprio CLI retornou `exit_code=2`: `the argument '--sandbox <SANDBOX_MODE>' cannot be used with '--approve-for-me'`. Resultado: 0 turnos do modelo, 0 tokens, 0 `tools/call` e nenhuma alteração persistente. Evidência detalhada: `28-approval-policy-probe.json`.

A Fase 3.12 adicionou um guard no executor e um validador offline. O guard rejeita a combinação antes do preflight; o validador consulta apenas `codex exec --help`. O resultado foi `PASS`, sem modelo iniciado ou quota consumida. `read-only` sem `--approve-for-me` foi aceito apenas pela análise de argumentos; o comportamento de aprovação MCP em runtime continua não validado.

A Fase 3.13 adicionou `tools/run_codex_mcp_interactive_probe.ps1`, usando `--ask-for-approval on-request` com `--sandbox read-only`, sem `--approve-for-me`. A execução permanece preparada, não iniciada. O status local também passou a comparar caminhos normalizados e resolvidos; divergências retornam `WRONG_WORKSPACE`. Na raiz correta, a verificação retornou `CURRENT`, `workspace_match=true`, 250 arquivos, 1789 símbolos e 2410 imports.

A única sonda interativa autorizada foi iniciada, mas o TUI encerrou antes do modelo por falta do pacote local completo do CLI. Nenhuma aprovação MCP, `tools/call` ou token foi observado. O Codex acrescentou temporariamente apenas `[tui] screen_reader_detection_done = true`; essa configuração foi removida. A normalização de EOF da edição impediu restaurar o hash byte-a-byte anterior (`0C389...`); o hash atual é `850C2E...`, limitação registrada em `31-interactive-probe-blocked.json`. O executor agora inclui `--no-daemon`; não houve segunda tentativa.

## Incidente: integração restrita Codex → PIE → Blender

A única sessão real autorizada com perfil temporário Blender-only passou pelo gateway. `initialize` e `tools/list` passaram; o lifecycle registrou dois `MCP_TOOL_CALL_RECEIVED` e duas respostas `result`, para `get_addon_status` e `get_scene_info`. Os dois oráculos retornaram sucesso, `workspace_match=true` e nenhuma ferramenta não autorizada foi executada. O provedor reportou 67.769 tokens de entrada, 59.136 em cache, 534 de saída, 338 de raciocínio e 18.647,696 ms. Evidência completa: [`32-restricted-blender-probe.json`](32-restricted-blender-probe.json).

Isso comprova o caminho Blender restrito, mas não certifica economia: Web não foi executado nesta sessão e os pares A/B continuam incompletos.

## Incidente: integração restrita Codex → PIE → Web

A única sessão real Web usou uma página local determinística e um perfil temporário com apenas `browser_navigate` e `browser_snapshot`. `initialize`, `tools/list`, navegação e snapshot passaram; o lifecycle registrou as duas chamadas no `pie-web-optimized`, sem ferramentas não autorizadas. O provedor reportou 59.695 tokens de entrada, 54.144 em cache, 746 de saída, 528 de raciocínio e 19.777,745 ms. Evidência: [`33-restricted-web-probe.json`](33-restricted-web-probe.json).

O probe offline do Playwright preservou referências nativas e reduziu caracteres de 17.585 para 1.256 (92,858%). Isso é uma métrica de caracteres, não uma medição de tokens; a economia permanece pendente de A/B.

## Auditoria offline dos A/B históricos

Os pares 2/3 de Blender e Web têm prompts, oráculos e uso do provedor comparáveis. Ainda assim, os artefatos não registram ferramentas/rota por execução; o SQLite histórico tem `0` observações Blender e `2` Web, e o gateway mudou desde o commit histórico. Eles permanecem evidência preliminar, não certificação causal do PIE.

O gate de rota foi endurecido no commit `d2f574d` e documentado em [`35-route-evidence-gate.md`](35-route-evidence-gate.md). A primeira sonda A/B no commit atual passou nos quatro preflights e no probe direto do gateway Blender, mas a captura Codex `blender-baseline-01` terminou em `RuntimeError` sem registro JSONL, lifecycle ou SQLite. A bateria foi interrompida sem retry; evidência: [`36-current-ab-initial-blocked.md`](36-current-ab-initial-blocked.md).

Depois foram preparados perfis efêmeros isolados com `enabled_tools`, sandbox `read-only` e somente o servidor do domínio. Os quatro preflights passaram no commit `ac02f4c`. O probe Web direto também passou quando chamado com `C:\Program Files\nodejs\npx.cmd`; evidência offline em [`37-current-offline-prep.json`](37-current-offline-prep.json). Nenhuma nova sessão Codex foi iniciada.

Uma nova sonda controlada Blender no commit `361e79d` iniciou o Codex, mas foi rejeitada pelo gate com `MCP route evidence failed; unexpected server or incomplete tool call`. A execução não deixou lifecycle porque o executor ainda não exportava os caminhos de diagnóstico para o processo Codex. Isso foi corrigido em `ed759c9`; a sonda não foi repetida. Evidência: [`38-current-probe-route-failure.json`](38-current-probe-route-failure.json).

Depois da correção, foram concluídos quatro registros reais em pares iniciais no commit `964f405`: Blender `58.346 → 45.073` tokens de entrada e Web `51.755 → 44.716`. Todos os quatro oráculos e rotas passaram. A economia preliminar foi Blender `22,749%` e Web `13,601%` em input. Evidência: [`39-initial-real-pairs.md`](39-initial-real-pairs.md). O par não é certificação final: falta replicação e os registros precedem a correção `6ce5afc` do store de lifecycle fora do worktree.

O contrato de correlação foi endurecido em `4c1e90c`: novas capturas levam `task_id` pelo cenário e `run_id` determinístico no próprio JSON e no SQLite, sem depender de IDs inventados pelo modelo. Evidência: [`40-task-run-correlation.json`](40-task-run-correlation.json).

O oráculo independente Blender também foi validado sem mutação: `PIE_AB_Cube` usa `PIE_AB_Material`, com roughness `0,35` e metallic `0,20`. O cenário de inspeção via `execute_blender_code` está preparado, mas ainda não foi executado como sessão Codex A/B. Evidência: [`41-blender-material-oracle.json`](41-blender-material-oracle.json).

Para certificar o commit atual, o plano fechado exige **12 novas sessões**: três pares Blender e três Web, seis baseline e seis optimized. O relatório detalhado é [`34-ab-offline-audit.md`](34-ab-offline-audit.md).

## Execução integrada baseline Blender — 2026-11-15

Foi executada uma única sessão baseline real com o controlador novo, sem retry. O Codex reportou `95.925` tokens de entrada, `82.560` em cache, `672` de saída e `19.964,993 ms`; `blender/get_scene_info` e `blender/execute_blender_code` concluíram e a captura forense foi preservada por `run_id=baseline-1c07733a5e3840e3ad9a9b79` e `pair_id=pair-81c43938155843a8bb299912`.

Entretanto, a leitura Blender independente posterior encontrou roughness `0.4000000059604645` e metallic `0.0`, contra o contrato `0.35` e `0.2`. O marcador textual do Codex passou, mas o oráculo independente falhou. A execução foi excluída de qualquer cálculo A/B; optimized não foi iniciado e não houve retry. Evidências: [`60-single-baseline-blender-acceptance.json`](60-single-baseline-blender-acceptance.json), [`60-single-baseline-blender.md`](60-single-baseline-blender.md) e o diretório forense indicado nesses relatórios.

O resultado atual é `BASELINE_BLENDER_FAILED_ORACLE`; a certificação geral permanece `NOT_CERTIFIED`.

## Baseline Blender corrigida — 2026-11-15

Após corrigir o prompt para ler o `BSDF_PRINCIPLED`, uma nova execução real independente foi válida. O Codex reportou `58.889` tokens de entrada, `35.840` em cache, `685` de saída e `17.451,210 ms`. As duas ferramentas Blender esperadas concluíram, e a leitura independente confirmou roughness `0.349999994` e metallic `0.200000002`.

Evidência: [`62-single-baseline-blender-fixed.md`](62-single-baseline-blender-fixed.md), [`63-single-optimized-blender.md`](63-single-optimized-blender.md) e [`64-blender-single-pair-comparison.json`](64-blender-single-pair-comparison.json). O par `pair-deda0256ba284175ade5d58d` foi executado; a baseline é válida e o braço optimized foi preservado como falha de evidência, sem retry.

## Custos

`null`: não foi fornecida tarifa verificável para `gpt-5.6-luna`. Quota/assinatura não foi convertida em preço.

## Compatibilidade Blender `structuredContent` — 2026-11-15

O bridge Blender foi corrigido para consultar `outputSchema` em `tools/list`. Quando não há schema declarado, ele reduz somente a apresentação textual e preserva `structuredContent`; quando há schema, faz `PASSTHROUGH`. Texto JSON estruturado, erros e conteúdo misto também permanecem íntegros. A suíte passou com 573 testes e 5 ignorados, sem sessão de modelo ou quota nesta etapa. Evidência: [`78-structured-content-compatibility.md`](78-structured-content-compatibility.md).

Essa alteração remove o bloqueio técnico offline, mas ainda não prova equivalência do cliente Codex nem economia de tokens. O próximo gate é o probe MCP real atualizado, seguido do A/B autorizado; a certificação continua `NOT_CERTIFIED`.

## Probe real Blender `structuredContent` — 2026-11-15

O probe com Blender 5.3 GUI descartável e a fixture real passou nos dois braços. `get_scene_info` declara `outputSchema` `object` com `result` obrigatório. O `structuredContent.result` é a mesma string de 1.522 caracteres presente em `content[0].text`; a resposta serializada mede 3.213 caracteres tanto no baseline quanto no PIE. Não houve compactação, recuperação ou chamadas duplicadas. Classificação: `PASSTHROUGH_SAFE`. Evidência completa: [`79-real-blender-structured-probe.md`](79-real-blender-structured-probe.md).

Conclusão: o A/B Blender não deve ser liberado como teste de economia enquanto esse contrato exigir a observação textual integral. A solução correta passa por uma ferramenta/contrato resumido próprio ou por uma resposta upstream sem essa exigência; remover `structuredContent` seria uma violação do contrato.

## Consulta seletiva Blender — 2026-11-15

Foi implementada e validada a ferramenta PIE-owned `pie_blender_query_scene`, sem alterar `get_scene_info`. Ela declara contrato de entrada/saída próprio, filtros allowlisted, campos selecionáveis e paginação determinística. Na fixture real de 64 objetos, quatro páginas retornaram `20/20/20/4` itens, com offsets `0/20/40/60`, `next_offset=null` na última página e tipos aprovados pelo oráculo. Cada consulta do cliente gerou uma única execução interna read-only. Evidência: [`80-real-blender-selective-query.md`](80-real-blender-selective-query.md).

Essa é uma capacidade seletiva, não compactação transparente. O payload da primeira página foi 1.692 caracteres contra 3.213 de `get_scene_info`, mas essa diferença entre contratos não é economia de tokens certificada. O A/B Blender continua bloqueado até definir uma tarefa comparável que use esse contrato de forma explícita.

## Simulação offline Blender A/B/C — 2026-11-15

As três tarefas propostas passaram contra a fixture real: localização A em 1 consulta, filtragem B em 1 consulta e inventário C em 4 páginas (`20/20/20/4`), cobrindo 64 objetos sem duplicações. Os payloads acumulados foram 376, 1.263 e 5.620 caracteres, respectivamente; essas medidas são locais e não são tokens. Evidência: [`81-blender-selective-task-simulation.md`](81-blender-selective-task-simulation.md).

O próximo piloto pode começar pela tarefa A com um único par real, desde que o braço optimized use explicitamente o contrato seletivo e o baseline use as ferramentas originais. A certificação permanece `NOT_CERTIFIED`.

## Auditoria de código da consulta seletiva — 2026-11-15

Os oráculos foram fortalecidos para comparar valores exatos da fixture, e o simulador agora declara explicitamente `optimized_only`/`NOT_RUN` para A/B. A ponte Blender foi auditada, com regressões para uma execução upstream por consulta e rejeição de argumentos inválidos antes do dispatch. Suíte atual: 583 aprovados e 5 ignorados. Parecer: `APPROVED_WITH_RESERVATIONS`; A/B pago permanece pendente. Evidência: [`82-selective-query-code-audit.md`](82-selective-query-code-audit.md).

## Plano do primeiro par A/B Blender — 2026-11-15

Foi preparado, sem iniciar modelo, um par manual da tarefa A. Baseline usa `blender/get_scene_info`; optimized usa `pie-blender-optimized/pie_blender_query_scene`. O prompt e a fixture são iguais, o oráculo compara nome, tipo, coordenadas e material exatos, e o plano exige uso real do provedor e rota correlacionada. O experimento está explicitamente classificado como comparação de produto de consulta seletiva, não compactação transparente. Evidência: [`83-blender-selective-a-plan.md`](83-blender-selective-a-plan.md).

## Revisão do plano A — correções antes de quota

Após auditoria do commit `a86fce5`, o plano foi ajustado antes de qualquer execução: a resposta agora deve ser um JSON verificável; o oráculo aceita somente os quatro campos e valores exatos; baseline e optimized geram allowlists estáticas exclusivas; e `pair_id`, `attempt_nonce` e `run_id` são novos em cada preparação. O handshake `tools/list` e a telemetria `tools/call` ainda são gates obrigatórios de runtime. Estado: `PLAN_REVIEW_BLOCKED_FOR_PAID_EXECUTION` até essa comprovação. Suítes focadas: 19 aprovados.

## Probe sem modelo dos perfis — 2026-11-15

O baseline passou `initialize`, `tools/list` e `get_scene_info` diretamente. O optimized passou `initialize` e `tools/list`, mas `pie_blender_query_scene` retornou `PIE_QUERY_UNAVAILABLE` porque o Blender live não devolveu o marcador esperado; a cena atual também não contém o objeto da fixture `PIE_Large_Cube_00`. Uma chamada real proibida a `get_scene_info` foi rejeitada por `PIE_TOOL_NOT_EXPOSED` sem alcançar o upstream, e o teste de contrato confirmou `structuredContent` junto com `content`. Nenhuma sessão de modelo ou quota foi consumida. Estado: `BLOCKED_FOR_PAID_EXECUTION`. Evidência: [`84-no-model-profile-probe.md`](84-no-model-profile-probe.md).

O probe foi repetido após carregar uma fixture descartável real no Blender 5.3 e regenerar os perfis contra o SHA completo `02e1b4835d2bdcee34812d4effccf7c0e1b4a4ca`. Baseline e optimized passaram `initialize`, `tools/list`, `tools/call` e o oráculo da fixture; optimized anunciou somente uma ferramenta e retornou `structuredContent`. O gate sem modelo passou, mas tokens A/B continuam pendentes. Evidência: [`85-no-model-fixture-probe.md`](85-no-model-fixture-probe.md).

## Próximos passos seguros

## Revalidação final sem modelo — 2026-11-15

Os perfis baseline e optimized passaram novamente por `initialize`, `tools/list` e `tools/call` usando a fixture descartável real do Blender 5.3. O baseline expôs 10 ferramentas e o optimized expôs somente `pie_blender_query_scene`; ambos localizaram `PIE_Large_Cube_00` e retornaram `structuredContent`. A tentativa proibida de `get_scene_info` foi rejeitada por `PIE_TOOL_NOT_EXPOSED` antes do upstream. Nenhuma sessão de modelo ou quota foi consumida. Evidência: [`86-no-model-profile-revalidation.md`](86-no-model-profile-revalidation.md).

O preflight passou a validar a identidade da árvore `src/`, permitindo commits posteriores apenas de relatórios sem invalidar perfis. A suíte completa foi executada novamente: `583` aprovados e `5` ignorados. Tokens reais de provedor e economia A/B continuam pendentes; o veredito permanece `NOT_CERTIFIED`.

O plano `83-blender-selective-a-plan.json` foi alinhado com essa evidência: `runtime_validation=PASS_NO_MODEL_GATE`, com `tools/list`, `tools/call` e rejeição da ferramenta proibida em `PASS`. O campo `latest_plan_review` do consolidado agora é `READY_FOR_MANUAL_PILOT`; isso não altera o estado de certificação, pois o A/B com modelo ainda não foi executado.

## Correção do isolamento efetivo — 2026-11-15

A auditoria do incidente 88 identificou que o preflight anterior mesclava servidores herdados e verificava apenas a existência do servidor esperado. A correção passou `enabled_tools` para cada servidor, adicionou desabilitação explícita de servidores herdados e passou a consultar `codex mcp list --json` sem modelo. Baseline e optimized agora têm exatamente um servidor habilitado cada, com allowlists distintas. Evidência: [`90-effective-codex-mcp-isolation.md`](90-effective-codex-mcp-isolation.md).

A suíte atualizada passou com `586` testes e `5` ignorados. O incidente 88 continua inválido para A/B; nenhum novo benchmark pago foi iniciado após a correção.

## Primeiro piloto após isolamento — 2026-11-15

O preflight e a rota baseline passaram com isolamento efetivo: somente `blender/get_scene_info` foi chamado. A execução, porém, falhou no oráculo da resposta JSON do Codex (`oracle_pass=false`). Foram reportados `60.601` tokens de entrada, `54.656` cacheados e `503` de saída. O optimized não foi executado e não há economia A/B calculável. Evidência: [`92-blender-baseline-isolated.md`](92-blender-baseline-isolated.md). O estado permanece `NOT_CERTIFIED`.

Após essa falha, o executor foi aprimorado para registrar diagnóstico estrutural sanitizado do oráculo — formato, tamanho, hash, chaves ausentes/extras e tipos — sem armazenar a resposta. A suíte passou com `587` testes e `5` ignorados.

## Primeiro piloto Blender com modelo — 2026-11-15

O preflight final passou nos dois braços sem iniciar modelo. A primeira sessão baseline, porém, foi invalidada pelo roteamento: observou `pie-blender-optimized/pie_blender_query_scene` com falha antes de `blender/get_scene_info` completar. Foram consumidos `1` sessão e `142.200` tokens de entrada reportados, mas o resultado não é elegível para economia A/B. O optimized não foi executado e não houve retry. Evidência: [`88-blender-baseline-r1.md`](88-blender-baseline-r1.md). A certificação permanece `NOT_CERTIFIED`.

1. Escolher, com nova autorização, uma combinação de aprovação suportada pela versão instalada: ou `--approve-for-me` sem `--sandbox`, ou uma sessão interativa `on-request` que aceite a aprovação manual. Não remover proteções indiscriminadamente.
2. Fazer cada captura Codex autorizada usar `--telemetry-workspace`, para que o import validado ocorra automaticamente no mesmo fluxo da execução.
3. Corrigir offline a captura Codex→MCP e repetir somente uma sonda controlada antes de retomar os pares; a bateria atual foi interrompida na primeira captura.
4. Medir overhead real por operação e verificar inicialização contínua dos dois gateways.

Relatórios detalhados: [`09-blender-real-ab.json`](09-blender-real-ab.json), [`10-web-real-ab.json`](10-web-real-ab.json), [`11-token-certification.json`](11-token-certification.json), [`12-cost-efficiency.json`](12-cost-efficiency.json), [`14-offline-root-cause.md`](14-offline-root-cause.md), [`22-codex-mcp-probe-result.json`](22-codex-mcp-probe-result.json), [`23-mcp-offline-forensics.md`](23-mcp-offline-forensics.md), [`24-mcp-bootstrap-validation.json`](24-mcp-bootstrap-validation.json), [`25-mcp-offline-integration.json`](25-mcp-offline-integration.json), [`28-approval-policy-probe.json`](28-approval-policy-probe.json), [`29-cli-compatibility.json`](29-cli-compatibility.json), [`35-route-evidence-gate.md`](35-route-evidence-gate.md), [`36-current-ab-initial-blocked.md`](36-current-ab-initial-blocked.md), [`37-current-offline-prep.json`](37-current-offline-prep.json), [`38-current-probe-route-failure.json`](38-current-probe-route-failure.json), [`39-initial-real-pairs.md`](39-initial-real-pairs.md), [`40-task-run-correlation.json`](40-task-run-correlation.json) e [`41-blender-material-oracle.json`](41-blender-material-oracle.json).
