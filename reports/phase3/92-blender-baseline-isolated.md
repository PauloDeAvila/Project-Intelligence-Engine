# PIE Fase 3 — Baseline Blender isolada: rota correta, oráculo falhou

Data: 2026-11-15

## Resultado

`BASELINE_BLENDER_FAILED`. O isolamento funcionou, mas a resposta do Codex não correspondeu ao oráculo JSON da tarefa.

| Métrica | Valor |
|---|---:|
| Pair ID | `pair-iso-32bb-blender-a` |
| Run ID | `baseline-iso-32bb-blender-a` |
| Input tokens | 60.601 |
| Input cacheado | 54.656 |
| Input não cacheado | 5.945 |
| Output tokens | 503 |
| Reasoning informado | 241 |
| Duração | 16.241,44 ms |
| Chamadas MCP | 1 |
| Rota | `blender/get_scene_info` — PASS |
| Oráculo da resposta | FAIL |
| Retry | 0 |

O oráculo independente da fixture permaneceu válido, mas `oracle_pass=false` para a resposta produzida pelo Codex. O conteúdo completo da resposta não foi armazenado; somente seu SHA-256 foi preservado, conforme a política de não armazenar respostas completas.

O optimized não foi executado. Não existe par A/B válido nem economia calculável.

Evidência: [`92-blender-baseline-isolated.json`](92-blender-baseline-isolated.json) e seu ledger associado.

Estado: `NOT_CERTIFIED`.
