# A/B Blender ao vivo — cena padrão

Foi executado um par real contra a cena Blender atual, sem alterá-la, usando o
mesmo modelo local `gambiarraapi/deepseek-v3.2`, o mesmo prompt e o mesmo
oráculo JSON.

| Métrica | Baseline | PIE |
|---|---:|---:|
| Tokens de entrada | 5.167 | 212 |
| Tokens de saída | 34 | 34 |
| Tokens totais | 5.201 | 246 |
| Latência | 2,8839 s | 2,9077 s |
| Chamadas MCP | 3 | 3 |
| Ferramentas anunciadas | 10 | 1 |
| Oráculo | PASS | PASS |

Economia total: **95,27%**. Economia de entrada: **95,897%**.

O resultado é uma única réplica controlada de uma cena padrão e permanece
`PILOT_VALID_NOT_CERTIFIED`. Não substitui a certificação oficial Codex nem o
benchmark da fixture grande `PIE_Large`.

Evidência bruta: `blender-live-default-cube-deepseek-20261117.json`.
