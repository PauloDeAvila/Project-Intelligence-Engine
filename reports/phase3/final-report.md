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

`pytest`: **537 passed, 5 skipped, 133 subtests** (via `PYTHONPATH=. uv run --with pytest pytest -q`). `compileall`: passou. O preflight agora bloqueia overlays com workspace divergente. O status local do checkout retornou `CURRENT`, com `workspace_match=true` e `index_root` igual a `workspace_root`. O servidor PIE MCP disponível nesta sessão continua reportando outra raiz (`C:\\Users\\phsra\\Documents\\Codex\\2026-11-14\\contrato-de-uso-ativo-do-project`), portanto não foi tratado como evidência deste checkout.

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

## Custos

`null`: não foi fornecida tarifa verificável para `gpt-5.6-luna`. Quota/assinatura não foi convertida em preço.

## Próximos passos seguros

1. Escolher, com nova autorização, uma combinação de aprovação suportada pela versão instalada: ou `--approve-for-me` sem `--sandbox`, ou uma sessão interativa `on-request` que aceite a aprovação manual. Não remover proteções indiscriminadamente.
2. Fazer cada captura Codex autorizada usar `--telemetry-workspace`, para que o import validado ocorra automaticamente no mesmo fluxo da execução.
3. Reexecutar somente os pares faltantes com nova autorização, pois o limite de 12 chamadas da autorização A/B foi consumido.
4. Medir overhead real por operação e verificar inicialização contínua dos dois gateways.

Relatórios detalhados: [`09-blender-real-ab.json`](09-blender-real-ab.json), [`10-web-real-ab.json`](10-web-real-ab.json), [`11-token-certification.json`](11-token-certification.json), [`12-cost-efficiency.json`](12-cost-efficiency.json), [`14-offline-root-cause.md`](14-offline-root-cause.md), [`22-codex-mcp-probe-result.json`](22-codex-mcp-probe-result.json), [`23-mcp-offline-forensics.md`](23-mcp-offline-forensics.md), [`24-mcp-bootstrap-validation.json`](24-mcp-bootstrap-validation.json), [`25-mcp-offline-integration.json`](25-mcp-offline-integration.json), [`28-approval-policy-probe.json`](28-approval-policy-probe.json) e [`29-cli-compatibility.json`](29-cli-compatibility.json).
