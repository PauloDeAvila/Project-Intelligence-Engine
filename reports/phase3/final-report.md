# PIE Fase 3 — certificação real e monitoramento

## Veredito

**NOT_CERTIFIED.** As 12 chamadas autorizadas terminaram com uso real reportado pelo provedor e os quatro oráculos estritamente comparáveis passaram. Porém, somente dois pares comparáveis foram obtidos por domínio; o critério exige três. A persistência SQLite também registrou apenas dois eventos Web `PASSTHROUGH`, sem eventos Blender desta bateria.

Na autorização complementar, foram consumidas 2 de 4 chamadas: o par Blender teve tokens reportados, mas todas as ferramentas MCP esperadas falharam nos dois braços. O oráculo de texto passou, mas isso não é suficiente para validar a tarefa. A bateria foi interrompida e o par Web não foi executado.

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

`pytest`: **535 passed, 5 skipped, 133 subtests**. `compileall`: passou. O preflight agora bloqueia overlays com workspace divergente. O índice local PIE foi reindexado para a raiz correta e ficou `CURRENT`; o servidor PIE MCP disponível nesta sessão continua apontando para outra raiz, limitação registrada.

## Diagnóstico Codex/MCP

A única chamada diagnóstica autorizada após a instrumentação falhou antes do spawn MCP porque o override transitório `-c` codificou `mcp_servers.pie-blender-optimized.args` como string (`expected a sequence`). Não houve handshake, `tools/list`, `tools/call` ou tokens reportados. O resultado não identifica a falha MCP original; uma nova tentativa exigiria autorização adicional e não deve ser feita automaticamente. O executor corrigido está preparado em `tools/run_codex_mcp_diagnostic.ps1`, mas não foi executado.

## Custos

`null`: não foi fornecida tarifa verificável para `gpt-5.6-luna`. Quota/assinatura não foi convertida em preço.

## Próximos passos seguros

1. Fazer cada captura Codex autorizada usar `--telemetry-workspace`, para que o import validado ocorra automaticamente no mesmo fluxo da execução.
2. Reexecutar somente os pares faltantes com nova autorização, pois o limite de 12 chamadas desta autorização foi consumido.
3. Medir overhead real por operação e verificar inicialização contínua dos dois gateways.

Relatórios detalhados: [`09-blender-real-ab.json`](09-blender-real-ab.json), [`10-web-real-ab.json`](10-web-real-ab.json), [`11-token-certification.json`](11-token-certification.json), [`12-cost-efficiency.json`](12-cost-efficiency.json), [`14-offline-root-cause.md`](14-offline-root-cause.md) e [`17-final-blender-attempt.json`](17-final-blender-attempt.json).
