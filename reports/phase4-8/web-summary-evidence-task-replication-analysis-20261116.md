# Web Summary Evidence Task — Replicação

O runner executou três pares válidos da fixture Web `summary` usando
`response_format: {"type":"json_object"}` e o provider local
`gambiarraapi/deepseek-v3.2`.

- Pares válidos: 3/3.
- Tokens baseline: 19.965.
- Tokens PIE: 18.001.
- Economia ponderada: 9,837%.
- Entrada: 19.872 → 17.820 tokens, redução de 10,326%.
- Saída: 93 → 181 tokens; aumento de 94,624%.
- Cache reportado: 15.240 → 5.570 tokens.
- Latência média: 4,1648 s → 2,4789 s, redução de 40,479%.
- Oráculos: 3/3 em ambos os braços.

O resultado é válido para esta tarefa determinística e mostra ganho total
modesto, apesar da redução de entrada. O aumento de saída e a diferença de
cache entre os braços impedem atribuir causalidade apenas à compactação. A
evidência é local, limitada a uma fixture e não substitui a certificação
oficial do Codex.

Evidência: `web-summary-evidence-task-replication-analysis-20261116.json`.
