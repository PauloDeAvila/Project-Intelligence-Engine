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
- Blender com seleção/interpretação: 3 pares locais válidos, uma chamada MCP
  por braço e duas inferências locais por braço.
- Web grande: 3 pares válidos com Playwright MCP `@playwright/mcp@0.0.85` e
  zero recuperações adicionais.
- Respostas incorretas do modelo fecham a execução sem retry.
- Nenhuma alteração destrutiva foi feita na cena Blender ou em páginas externas.
- A primeira suíte completa executou 641 testes, 5 ignorados e teve 1 erro
  ambiental `WinError 10053`; o teste isolado passou e a segunda suíte completa
  também passou com 641 testes e 0 erros. Evidência: [114-full-suite-validation-20261115.json](114-full-suite-validation-20261115.json).

## Telemetria e custos

O uso local vem de `prompt_eval_count` e `eval_count` do Ollama. Não há tarifa
verificada para converter tokens em dinheiro; custos permanecem `null`. A
A persistência local foi revalidada com 33 testes aprovados, cobrindo métricas
SQLite, lifecycle MCP, correlação task/run, recuperação de output, retenção e
isolamento após reinício. Isso não prova a importação de uso do provedor Codex.
Evidência: [113-telemetry-persistence-validation-20261115.json](113-telemetry-persistence-validation-20261115.json).

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
