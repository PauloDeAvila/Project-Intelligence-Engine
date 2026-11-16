# Piloto real DeepSeek 3.2 — par válido

Estado: `PILOT_VALID_NOT_CERTIFIED`.

Após tornar explícito o limite de saída (`512`) e usar o mesmo limite nos dois
braços, o baseline e o PIE passaram no oráculo em `3/3` tarefas do mesmo commit
do Textualize/Rich.

| Métrica | Baseline | PIE |
|---|---:|---:|
| Chamadas | 3 | 3 |
| Oráculo aprovado | 3/3 | 3/3 |
| Input tokens | 26.889 | 1.547 |
| Input cacheado | 22.660 | 1.335 |
| Input não cacheado | 4.229 | 212 |
| Output tokens | 213 | 133 |
| Total tokens | 27.102 | 1.680 |
| Latência mediana | 3,1989 s | 2,7034 s |

Economia medida:

- Input: `94,247%`.
- Input não cacheado: `94,987%`.
- Total: `93,801%`.
- Latência mediana: `15,49%` menor.

O resultado é uma medição válida de três pares para o provedor local Infinity,
com uso reportado e qualidade equivalente. Ainda não é certificação geral:
faltam tarefas Blender/Web, amostra estatística mais ampla e certificação
oficial do Codex.
