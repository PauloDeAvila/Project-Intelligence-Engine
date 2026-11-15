# PIE Fase 3 — Primeiro par Blender interrompido

Data: 2026-11-15

## Resultado

`BASELINE_BLENDER_FAILED`. A sessão do Codex iniciou e o provedor reportou uso, mas a execução foi invalidada pelo gate de roteamento. O braço baseline deveria chamar somente `blender/get_scene_info`.

| Métrica | Valor |
|---|---:|
| Sessões consumidas | 1 |
| Retry | 0 |
| Input tokens | 142.200 |
| Input cacheado | 113.408 |
| Input não cacheado | 28.792 |
| Output tokens | 736 |
| Reasoning output | 300 |
| Duração | 21.771,552 ms |
| Chamadas MCP observadas | 2 |

## Roteamento observado

1. `pie-blender-optimized/pie_blender_query_scene` — `failed`
2. `blender/get_scene_info` — `completed`

O evento optimized inesperado torna o braço baseline inválido. O optimized não foi executado, nenhum par foi aceito e a bateria foi interrompida sem retry.

Evidência JSON: [`88-blender-baseline-r1.json`](88-blender-baseline-r1.json). Ledger: [`88-blender-baseline-r1-budget-ledger.json`](88-blender-baseline-r1-budget-ledger.json).

## Interpretação

Os tokens são uso real reportado pelo provedor, mas não podem ser usados para calcular economia porque a condição baseline não teve cobertura de rota exclusiva. A hipótese operacional é contaminação do armazenamento de lifecycle compartilhado entre execuções; isso deve ser confirmado em uma futura tentativa com store novo e identidade de execução isolada. Não houve alteração da configuração persistente do usuário.

Estado global: `NOT_CERTIFIED`.
