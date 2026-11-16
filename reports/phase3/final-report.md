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
| Web large, 3 pares, fixture correta | 8.967 | 4.455 | **50,318%** | 6/6 |
| Web small, 3 pares | 2.502 | 2.502 | **0%** | 6/6 |

Os valores são tokens totais reportados pelo Ollama, não estimativas por
caracteres. A regressão Blender `query_scene` é válida e foi mantida. O
ensaio Web anterior de 9.259 → 4.417 permanece histórico; a tabela usa agora
a execução mais recente com a fixture declarada pelo cenário.

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

O benchmark local Blender com Qwen3:4B foi reexecutado no Blender 5.3 real
com 3 pares válidos. Baseline totalizou 1.125 tokens e o PIE 1.077, uma
economia local de 4,267%; ambos tiveram 3/3 oráculos aprovados, 3 chamadas
MCP e 6 requisições de modelo por braço. Essa medição não é certificação
Codex. Evidência: [126-blender-model-target-evidence-live-20261115.json](126-blender-model-target-evidence-live-20261115.json).

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

Uma nova tentativa Web local foi encerrada sem retry após dois pares válidos:
1.668 tokens em cada condição, 0% de economia e 4/4 oráculos aprovados. O
terceiro par falhou porque o Ollama ficou indisponível ou retornou JSON
inválido. Essa falha foi preservada e não substitui o relatório Web anterior
de três pares válidos; os resultados não devem ser combinados sem investigar
o problema de configuração/parsing. Evidência: [127-web-local-run-failed-after-two-pairs-20261115.json](127-web-local-run-failed-after-two-pairs-20261115.json).

Após tornar os erros do Ollama distinguíveis por status HTTP e JSON inválido,
uma sondagem única Web passou nos dois braços: 834 tokens baseline e 834 PIE,
0% de economia, 2 chamadas MCP por braço e oráculos semânticos aprovados.
Evidência: [128-web-local-single-pair-after-diagnostic-fix-20261115.json](128-web-local-single-pair-after-diagnostic-fix-20261115.json).

Depois foi executada a bateria correta da fixture Web large declarada pelo
cenário (`fixtures/phase3/web-large/index.html`): 3 pares, ordem alternada,
8.967 tokens baseline contra 4.455 PIE, economia local de 50,318%, 6/6
oráculos e zero recuperações. O ensaio anterior de 0% serviu a fixture
`fixtures/phase3/web` por engano e permanece separado. Evidência:
[129-web-large-correct-fixture-live-20261115.json](129-web-large-correct-fixture-live-20261115.json).

Após a alteração do diagnóstico Ollama, a suíte completa passou com 643 testes,
5 ignorados e 0 erros em 66,323 s. Os warnings de HTTP 500/401/403 pertencem
a testes simulados e não falharam a suíte; o diagnóstico interno de disco cheio
também foi preservado sem ser contado como erro unittest. Evidência:
[130-full-suite-after-ollama-diagnostics-20261115.json](130-full-suite-after-ollama-diagnostics-20261115.json).

O launcher Web agora valida um marcador exclusivo da fixture antes de iniciar
MCP ou modelo. Servir a fixture pequena no endereço da large foi rejeitado
antes de qualquer chamada; servir `fixtures/phase3/web-large` passou o
`ProbeOnly` em 3 repetições. Evidência: [131-web-fixture-preflight-guard-20261115.json](131-web-fixture-preflight-guard-20261115.json).

O guard também foi validado no sentido inverso: servir a fixture large no
endereço small foi rejeitado antes do MCP, enquanto a fixture small correta
passou um `ProbeOnly`. Evidência: [132-web-fixture-guard-bidirectional-20261115.json](132-web-fixture-guard-bidirectional-20261115.json).

O endpoint OpenAI-compatible local do harness em `127.0.0.1:8080/v1` também
foi integrado ao runner sem persistir credenciais. O modelo realmente listado
foi `gambiarraapi/glm-5.3-flash` (não DeepSeek). Um par Web large válido
resultou em 2.698 tokens baseline contra 1.397 PIE, economia de 48,221%,
oráculos 2/2 aprovados e 59 tokens de reasoning reportados no braço otimizado.
Isso é evidência de outro provedor, não certificação Codex. Evidência:
[133-web-harness-openai-compatible-20261115.json](133-web-harness-openai-compatible-20261115.json).

Após a integração do provider OpenAI-compatible, a suíte completa passou com
644 testes, 5 ignorados e 0 erros em 63,037 s. Os warnings HTTP são dos testes
simulados e não foram contados como falhas. Evidência:
[134-full-suite-after-external-provider-20261115.json](134-full-suite-after-external-provider-20261115.json).

O limite configurável de saída Web foi avaliado com o mesmo harness local e o
mesmo cenário grande. Com `max_chars=1600`, `1200` e `1000`, os pares válidos
produziram respectivamente 59,522%, 60,378% e 63,788% de economia total, com
oráculos aprovados. O limite `800` falhou fechado antes de iniciar o modelo
porque os fatos necessários não ficaram disponíveis; nenhum token de provedor
foi consumido nessa tentativa. Essas medições são do modelo
`gambiarraapi/glm-5.3-flash`, não do Codex, e não devem ser combinadas com a
certificação oficial. Evidências: [135](135-web-harness-maxchars-1600-20261115.json),
[136](136-web-harness-maxchars-1200-20261115.json),
[137](137-web-harness-maxchars-1000-20261115.json) e
[138](138-web-harness-maxchars-800-failed-closed-20261115.json).

Uma nova sondagem em `max_chars=900` e `850` manteve os oráculos aprovados e
elevou a economia para 64,381% e 65,208%, respectivamente. O valor de 850 é
o melhor ponto seguro observado nesta sequência; não representa certificação
geral nem deve ser extrapolado para páginas arbitrárias. Evidência:
[140](140-web-harness-maxchars-850-20261115.json).

A suíte completa após esse ajuste passou novamente com 644 testes, 5 ignorados
e 0 erros. Evidência: [139-full-suite-after-maxchars-20261115.json](139-full-suite-after-maxchars-20261115.json).

Auditoria requisito‑por‑requisito: [115-completion-audit-20261115.json](115-completion-audit-20261115.json).
