# Auditoria de conclusão — Fases 4–8

## Resultado

`PARTIAL_NOT_CERTIFIED`. O índice consultado pertence ao checkout correto e
está `CURRENT`, mas os critérios de aceitação do roadmap ainda não estão todos
provados.

| Fase | Estado atual | Lacuna determinante |
|---|---|---|
| 4 — Consolidação | `PARTIAL_EXTERNAL_CONTROLLED` | A sonda Codex Web passou; a sonda Blender roteou corretamente, mas o addon não estava disponível. |
| 5 — Memória multiagente | `PASS_EXTERNAL_CONTROLLED` | Codex oficial criou o checkpoint pelo PIE e o GLM recebeu somente o contexto compilado, sem histórico completo. |
| 6 — Cache incremental | `PASS_EXTERNAL_CONTROLLED_SINGLE_PAIR` | Há prova real após reinício, mas somente um par. |
| 7 — Execução local | `PASS_LOCAL` | Allowlist, replay, timeouts, segurança e p95 local passaram. |
| 8 — Certificação contínua | `PARTIAL_NOT_CERTIFIED` | Existem gates locais válidos, mas falta A/B oficial do Codex e generalização estatística. |

## Evidência mais recente

- Índice PIE: `CURRENT`, `workspace_match=true`, 270 arquivos, 2.251 símbolos,
  2.610 imports, sem diagnósticos.
- Codex → `pie-web-optimized`: navegação, dois snapshots e clique passaram na
  fixture local; título `PIE Phase 3 Fixture` e marcador `PIE_WEB_FIXTURE_V1`.
- Codex → `pie-blender-optimized`: roteamento observado, mas `get_addon_status`
  e `get_scene_info` falharam sem processo Blender conectado.
- Suíte de regressão mais recente: 718 passed, 4 skipped e 126 subtests.

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
continua ausente neste host, portanto a guarda passou em modo fail-closed, mas
o dispatch vivo ainda não foi repetido.
