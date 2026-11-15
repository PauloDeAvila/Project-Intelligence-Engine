# PIE Fase 3 — relatório consolidado atual

## Veredito

**NOT_CERTIFIED**.

Os gateways Blender e Web foram exercitados localmente com Ollama `qwen3:4b`,
com uso reportado pelo provedor local e oráculos determinísticos. Isso não
substitui a certificação A/B do Codex com `gpt-5.6-luna`.

## Resultados locais

| Domínio/cenário | Baseline | PIE | Economia | Correção |
|---|---:|---:|---:|---:|
| Blender exact evidence, 3 tarefas | 1.125 | 1.077 | **4,267%** | 6/6 |
| Blender query scene, 3 pares | 1.941 | 2.340 | **−20,556%** | 6/6 |
| Web large, 3 pares | 9.259 | 4.417 | **52,295%** | 6/6 |
| Web small, 3 pares | 2.502 | 2.502 | **0%** | 6/6 |

Os valores são tokens totais reportados pelo Ollama, não estimativas por
caracteres. A regressão Blender `query_scene` é válida e foi mantida.

## Cobertura

- Blender determinístico: 3 tarefas, 6 chamadas MCP e 6 oráculos aprovados.
- Blender determinístico real: a fixture descartável no Blender 5.3 produziu 3 tarefas, 6 chamadas MCP e 6/6 oráculos aprovados; baseline usou `execute_blender_code` e PIE usou `pie_blender_get_object`. Evidência: [116-blender-live-deterministic-routing-20261115.json](116-blender-live-deterministic-routing-20261115.json). Como não houve inferência, isso não é uma medição de economia.
- Blender com seleção/interpretação: 3 pares locais válidos, uma chamada MCP
  por braço e duas inferências locais por braço.
- Web grande: 3 pares válidos com Playwright MCP `@playwright/mcp@0.0.85` e
  zero recuperações adicionais.
- Web MCP real: 3 repetições alternadas, 12 chamadas de ferramenta, zero recuperações e zero inferências; baseline e PIE usaram `browser_navigate` e `browser_snapshot` contra a fixture local. Evidência: [117-web-live-mcp-routing-20261115.json](117-web-live-mcp-routing-20261115.json).
- Respostas incorretas do modelo fecham a execução sem retry.
- Nenhuma alteração destrutiva foi feita na cena Blender ou em páginas externas.
- A primeira suíte completa executou 641 testes, 5 ignorados e teve 1 erro
  ambiental `WinError 10053`; o teste isolado passou e a segunda suíte completa
  também passou com 641 testes e 0 erros. Evidência: [114-full-suite-validation-20261115.json](114-full-suite-validation-20261115.json).
- Após a correção de identidade do runner, a suíte completa passou novamente:
  641 testes, 5 ignorados e 0 erros; os 27 testes focados do runner também
  passaram. Evidência: [119-correlation-runner-validation-20261115.json](119-correlation-runner-validation-20261115.json).

## Telemetria e custos

O uso local vem de `prompt_eval_count` e `eval_count` do Ollama. Não há tarifa
verificada para converter tokens em dinheiro; custos permanecem `null`. A
A persistência local foi revalidada com 33 testes aprovados, cobrindo métricas
SQLite, lifecycle MCP, correlação task/run, recuperação de output, retenção e
isolamento após reinício. Isso não prova a importação de uso do provedor Codex.
Evidência: [113-telemetry-persistence-validation-20261115.json](113-telemetry-persistence-validation-20261115.json).

No probe real Blender, os três processos PIE registraram `run_id`, `pair_id`,
`task_id`, `condition` e `gateway_server` no lifecycle SQLite/JSONL. O baseline
original ficou sem telemetria PIE por desenho; essa lacuna está explicitamente
classificada como `UNINSTRUMENTED_ORIGINAL_SERVER`. Um encerramento upstream com
`exit_code=1` ocorreu depois de uma resposta MCP válida e foi preservado para
investigação. Evidência: [118-telemetry-correlation-live-routing-20261115.json](118-telemetry-correlation-live-routing-20261115.json).

No probe Web de uma repetição, `browser_navigate` e `browser_snapshot` também
foram persistidos com identidade completa no gateway otimizado. O baseline
permanece sem eventos PIE por usar o servidor original. O wrapper de limpeza
retornou `-1` ao encerrar a fixture, embora o probe interno tenha produzido o
resultado MCP válido; isso não é tratado como certificação. Evidência:
[120-web-telemetry-correlation-20261115.json](120-web-telemetry-correlation-20261115.json).

A suíte completa após a instrumentação Web passou novamente com 641 testes,
5 ignorados e 0 erros. Evidência: [121-web-correlation-full-suite-20261115.json](121-web-correlation-full-suite-20261115.json).

O preflight oficial sem modelo encontrou `WRONG_WORKSPACE` na configuração
persistentemente instalada: as rotas apontam para outro checkout. Um perfil
efêmero, sem alterar `config.toml`, passou para Blender e Web com sandbox
`read-only`, somente as ferramentas esperadas e zero quota consumida. Evidência:
[122-codex-routing-preflight-20261115.json](122-codex-routing-preflight-20261115.json).

Depois do preflight efêmero, as duas rotas PIE persistentes foram corrigidas
para este checkout. O arquivo original foi preservado com SHA-256 registrado;
Blender e Web passaram novamente no preflight sem iniciar modelo. O rollback
está documentado no relatório [123-persistent-codex-routing-activation-20261115.json](123-persistent-codex-routing-activation-20261115.json).

Uma revalidação posterior das rotas persistentes também passou para Blender e
Web, sem iniciar modelo e sem consumir quota. O Blender expôs somente
`get_addon_status` e `get_scene_info`; o Web expôs somente
`browser_navigate` e `browser_snapshot`, com a fixture HTTP respondendo.
Evidência: [124-persistent-route-revalidation-20261115.json](124-persistent-route-revalidation-20261115.json).

A suíte completa foi reexecutada no commit corrente e passou com 641 testes,
5 ignorados e 0 erros em 67,539 s. A saída também contém um diagnóstico
interno `BLOCKED_WITH_EVIDENCE/disk full`, mas o processo unittest terminou
com `OK`; esse diagnóstico não foi contado como falha de teste. Evidência:
[125-full-suite-revalidation-20261115.json](125-full-suite-revalidation-20261115.json).

O overhead estrutural de catálogo foi medido sem modelo: Blender reduziu
`tools/list` de 18.982 para 3.792 caracteres e Web de 21.177 para 1.738.
Esses valores são tamanho estrutural, não latência nem tokens cobrados. A
evidência está em [111-tool-overhead-20261115.json](111-tool-overhead-20261115.json).

Uma amostra temporal adicional mediu `initialize` em 4.658 ms baseline e
4.791 ms optimized no Blender, e 837 ms baseline e 1.013 ms optimized no Web.
O delta de inicialização foi, portanto, aproximadamente +132,6 ms e +176,1 ms.
`tools/list` ficou abaixo de 100 ms nos dois domínios. Isso mede inicialização
de sessão, não overhead de cada `tools/call`; a evidência está em
[112-tool-overhead-timing-20261115.json](112-tool-overhead-timing-20261115.json).

## Comandos reproduzíveis

```powershell
uv run python -m unittest tests.test_blender_choice_agent tests.test_blender_choice_stdio tests.test_blender_routing tests.test_local_ollama_benchmark tests.test_pie_domain_gateway tests.test_pie_live_certification -q
.\tools\run_blender_choice_agent.ps1 -BlenderPort 9993 -RouteMode model_target_evidence -Model qwen3:4b -NumCtx 8192 -MaxTasks 3
.\tools\run_phase3_local.ps1 -Domain web -WebVariant large -NpxExe 'C:\Program Files\nodejs\npx.cmd' -Model qwen3:4b -Repetitions 3 -SchemaScope profile
```

## Limitações

- A certificação oficial Codex permanece pendente por falta de A/B completo
  válido com o provedor real.
- O índice PIE MCP desta sessão aponta para outra raiz; a limitação foi
  registrada e a validação usou o checkout local e testes executáveis.
- A meta de 85%/97% não foi atingida de forma geral. Os resultados incluem
  economia, neutralidade e regressão conforme o workload.

Evidências detalhadas: [109-local-routing-and-web-measurement-20261115.md](109-local-routing-and-web-measurement-20261115.md).

Auditoria requisito‑por‑requisito: [115-completion-audit-20261115.json](115-completion-audit-20261115.json).
