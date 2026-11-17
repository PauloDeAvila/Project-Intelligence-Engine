# Auditoria de conclusão — Fases 4–8

## Resultado

`PARTIAL_NOT_CERTIFIED`. O índice consultado pertence ao checkout correto e
está `CURRENT`, mas os critérios de aceitação do roadmap ainda não estão todos
provados.

| Fase | Estado atual | Lacuna determinante |
|---|---|---|
| 4 — Consolidação | `PARTIAL_EXTERNAL_CONTROLLED` | Rotas Web e Blender passaram pelo executor isolado; persistência, recuperação e limpeza de configuração foram comprovadas. |
| 5 — Memória multiagente | `PASS_EXTERNAL_CONTROLLED` | Codex oficial criou o checkpoint pelo PIE e o GLM recebeu somente o contexto compilado, sem histórico completo. |
| 6 — Cache incremental | `PASS_EXTERNAL_CONTROLLED_SINGLE_PAIR` | Há prova real após reinício, mas somente um par. |
| 7 — Execução local | `PASS_LOCAL` | Allowlist, replay, timeouts, segurança e p95 local passaram. |
| 8 — Certificação contínua | `PARTIAL_NOT_CERTIFIED` | Dois pares Blender e um Web oficiais passaram os oráculos, mas a amostra está incompleta e o Web apresentou regressão. |

## Evidência mais recente

- Índice PIE: `CURRENT`, `workspace_match=true`, 280 arquivos, 2.280 símbolos,
  2.646 imports, sem diagnósticos.
- Codex → `pie-web-optimized`: navegação, dois snapshots e clique passaram na
  fixture local; título `PIE Phase 3 Fixture` e marcador `PIE_WEB_FIXTURE_V1`.
- Codex → `pie-blender-optimized`: dois pares válidos chegaram ao Blender 5.3,
  passaram status, consulta e oráculo; uma terceira tentativa foi rejeitada por
  chamada `get_scene_info` duplicada.
- Suíte de regressão mais recente: 727 passed, 4 skipped e 126 subtests.

## Regra de certificação

Os pilotos locais de GLM, DeepSeek, Blender e Web são evidências de uso real e
permanecem preservados, mas não são promovidos a certificação oficial Codex.
Nenhum token ausente foi estimado e nenhum resultado negativo foi descartado.

Evidência estruturada: `completion-audit-20261117.json` e
`validation.json`.

## Mitigação do risco de preflight

`preflight_codex()` agora executa uma sonda TCP local limitada para o endpoint
Blender MCP antes de iniciar o provider. Endpoint indisponível retorna
`PRECHECK_BLENDER_UPSTREAM_UNAVAILABLE` e bloqueia a sessão sem consumo do
provider. O padrão é `127.0.0.1:9876`; endpoints customizados usam
`BLENDER_MCP_HOST` e `BLENDER_MCP_PORT`.

A guarda foi validada por 20 testes focados e pela suíte completa. O Blender
está disponível ao vivo em `127.0.0.1:9876` e o dispatch pelo PIE foi repetido
com oráculos aprovados.

## Atualização posterior — evidência oficial Codex

O executor isolado cria um `CODEX_HOME` temporário com somente o servidor
selecionado, preserva o modelo e esforço configurados e remove o diretório ao
terminar.

No Blender, dois pares válidos agregaram `239.237` tokens baseline contra
`132.814` optimized, economia de `44,484%`; a latência média optimized ficou
`9,165%` maior. No Web, o par controlado agregou `63.601` contra `92.520`
tokens, regressão de `45,469%`, embora os dois oráculos tenham passado.

A repetição Blender R3 foi marcada inválida porque o baseline executou três
chamadas MCP em vez das duas esperadas. O braço optimized não foi iniciado e
não houve retry automático. A certificação geral continua `NOT_CERTIFIED` até
completar as repetições e investigar essa variabilidade de rota.

Evidências: `codex-blender-default-aggregate-20261117.json`,
`codex-blender-default-r3-invalid-20261117.json` e
`codex-web-local-controlled-pair-20261117.json`.
