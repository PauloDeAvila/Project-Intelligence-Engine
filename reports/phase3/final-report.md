# PIE Fase 3 — certificação real e monitoramento

## Veredito

**NOT_CERTIFIED.** As 12 chamadas autorizadas terminaram com uso real reportado pelo provedor e os quatro oráculos estritamente comparáveis passaram. Porém, somente dois pares comparáveis foram obtidos por domínio; o critério exige três. A persistência SQLite também registrou apenas dois eventos Web `PASSTHROUGH`, sem eventos Blender desta bateria.

Na autorização complementar, foram consumidas 2 de 4 chamadas: o par Blender teve tokens reportados, mas todas as ferramentas MCP esperadas falharam nos dois braços. O oráculo de texto passou, mas isso não é suficiente para validar a tarefa. A bateria foi interrompida e o par Web não foi executado. Uma autorização posterior para uma única sonda de aprovação não chegou ao modelo: o CLI recusou a combinação `--sandbox read-only` + `--approve-for-me` antes do dispatch. Não houve retry.

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

`pytest`: **538 passed, 5 skipped, 133 subtests** (via `uv run --with pytest python -m pytest -q`). A execução sem o caso HTTP intermitente conhecido passou com **537 passed, 5 skipped, 1 deselected, 133 subtests**. `compileall`: passou. O preflight agora bloqueia overlays com workspace divergente. O status local do checkout retornou `CURRENT`, com `workspace_match=true` e `index_root` igual a `workspace_root`. O servidor PIE MCP disponível nesta sessão continua reportando outra raiz (`C:\\Users\\phsra\\Documents\\Codex\\2026-11-14\\contrato-de-uso-ativo-do-project`), portanto não foi tratado como evidência deste checkout. Evidência adicional: `42-validation-after-runner-fix.json`.

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

Para certificar o commit atual, o plano fechado exige **12 novas sessões**: três pares Blender e três Web, seis baseline e seis optimized. O relatório detalhado é [`34-ab-offline-audit.md`](34-ab-offline-audit.md). Não foram executados modelos nesta auditoria.

## Custos

`null`: não foi fornecida tarifa verificável para `gpt-5.6-luna`. Quota/assinatura não foi convertida em preço.

## Próximos passos seguros

1. Escolher, com nova autorização, uma combinação de aprovação suportada pela versão instalada: ou `--approve-for-me` sem `--sandbox`, ou uma sessão interativa `on-request` que aceite a aprovação manual. Não remover proteções indiscriminadamente.
2. Fazer cada captura Codex autorizada usar `--telemetry-workspace`, para que o import validado ocorra automaticamente no mesmo fluxo da execução.
3. Corrigir offline a captura Codex→MCP e repetir somente uma sonda controlada antes de retomar os pares; a bateria atual foi interrompida na primeira captura.
4. Medir overhead real por operação e verificar inicialização contínua dos dois gateways.

Relatórios detalhados: [`09-blender-real-ab.json`](09-blender-real-ab.json), [`10-web-real-ab.json`](10-web-real-ab.json), [`11-token-certification.json`](11-token-certification.json), [`12-cost-efficiency.json`](12-cost-efficiency.json), [`14-offline-root-cause.md`](14-offline-root-cause.md), [`22-codex-mcp-probe-result.json`](22-codex-mcp-probe-result.json), [`23-mcp-offline-forensics.md`](23-mcp-offline-forensics.md), [`24-mcp-bootstrap-validation.json`](24-mcp-bootstrap-validation.json), [`25-mcp-offline-integration.json`](25-mcp-offline-integration.json), [`28-approval-policy-probe.json`](28-approval-policy-probe.json), [`29-cli-compatibility.json`](29-cli-compatibility.json), [`35-route-evidence-gate.md`](35-route-evidence-gate.md), [`36-current-ab-initial-blocked.md`](36-current-ab-initial-blocked.md), [`37-current-offline-prep.json`](37-current-offline-prep.json), [`38-current-probe-route-failure.json`](38-current-probe-route-failure.json), [`39-initial-real-pairs.md`](39-initial-real-pairs.md), [`40-task-run-correlation.json`](40-task-run-correlation.json) e [`41-blender-material-oracle.json`](41-blender-material-oracle.json).
