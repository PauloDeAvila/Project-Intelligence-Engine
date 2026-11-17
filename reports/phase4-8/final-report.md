# PIE Context Runtime — relatório consolidado das Fases 4–8

## Veredito

`PARTIAL_NOT_CERTIFIED` / `NOT_CERTIFIED`.

As fases 4–7 têm evidências locais ou externas controladas para os estados
indicados abaixo. A Fase 8 ainda não atende ao critério de amostra e
consistência exigido para certificação geral.

| Fase | Estado | Evidência principal |
|---|---|---|
| 4 — Consolidação | `PARTIAL_EXTERNAL_CONTROLLED` | Executor Codex isolado, recuperação Blender, rotas Web/Blender e persistência local |
| 5 — Memória multiagente | `PASS_EXTERNAL_CONTROLLED` | Handoff Codex → GLM, checkpoints e isolamento entre projetos |
| 6 — Cache incremental | `PASS_EXTERNAL_CONTROLLED_SINGLE_PAIR` | Cache por hash e um par real após reinício |
| 7 — Execução local | `PASS_LOCAL` | Allowlists, limites, replay, timeouts e p95 SQLite abaixo de 100 ms |
| 8 — Certificação contínua | `PARTIAL_NOT_CERTIFIED` | Dois pares Blender válidos e um Web válido; amostra incompleta |

## A/B oficial Codex

Modelo: `gpt-5.6-luna`; esforço: `medium`; uso: tokens reportados em
`turn.completed`; custo financeiro: `null`, sem tarifa verificada.

### Blender

Dois pares válidos passaram os oráculos independentes:

- Baseline: `239.237` tokens totais agregados.
- PIE: `132.814` tokens totais agregados.
- Economia agregada: **44,484%**.
- Input não cacheado: `33.866` → `14.752` tokens.
- Latência média: PIE `9,165%` maior.
- Oráculos: `4/4`.

A repetição R3 foi rejeitada porque o baseline fez três chamadas MCP:
`get_addon_status`, `get_scene_info`, `get_scene_info`. O braço optimized não
foi executado e não houve retry.

### Web

O par controlado usou apenas a fixture local em `127.0.0.1:8766`:

- Baseline: `63.601` tokens.
- PIE: `92.520` tokens.
- Economia: **−45,469%** — regressão real.
- Latência: PIE `0,023%` maior.
- Chamadas: quatro em cada braço.
- Oráculos: `2/2`.
- Páginas externas modificadas: não.

O resultado negativo permanece no relatório e impede afirmar economia Web
genérica.

## Implementação e validação

- `11c6d80`: permite sequências legítimas com snapshots Web repetidos.
- `16c9b1b`: atualiza o relatório Markdown consolidado.
- `103028f`: consolida este relatório final.
- Índice PIE: `CURRENT`, `workspace_match=true`, 280 arquivos, 2.280 símbolos,
  2.646 imports, sem diagnósticos.
- Suíte: `727 passed, 4 skipped, 126 subtests passed`.

Comando reproduzível:

```powershell
$env:PYTHONPATH = "."
uv run pytest -q --basetemp .pytest-tmp-full-web-fix
uv run python -m pie.interfaces.cli status --root .
```

## Pendências determinantes

1. Investigar offline a chamada Blender duplicada antes de consumir nova quota.
2. Completar uma repetição Blender e duas Web com IDs e condições equivalentes.
3. Recalcular a certificação somente com pares válidos e oráculos aprovados.
4. Manter `NOT_CERTIFIED` enquanto a amostra oficial permanecer incompleta.

Evidências detalhadas: `validation.json`, `completion-audit-20261117.json`,
`codex-blender-default-aggregate-20261117.json`,
`codex-blender-default-r3-invalid-20261117.json` e
`codex-web-local-controlled-pair-20261117.json`.
