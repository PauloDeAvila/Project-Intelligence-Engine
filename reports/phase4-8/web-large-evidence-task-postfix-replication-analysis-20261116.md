# Web Large Evidence Task — Replicação pós-correção

Após a correção que preserva referências interativas em snapshots compactados,
três pares reais passaram o oráculo em ambos os braços.

- Tokens: 23.389 → 18.209.
- Economia ponderada: 22,147%.
- Entrada: 23.086 → 18.073, redução de 21,714%.
- Saída: 303 → 136, redução de 55,116%.
- Oráculos: 3/3 em ambos os braços.
- Latência média: 3,3924 s → 10,2211 s; regressão de 201,29%.

O terceiro braço otimizado demorou 23,1548 s e domina a média. Este conjunto
foi executado antes da adição dos campos do gate forense; por isso permanece
como piloto válido, mas não como suíte `CERTIFIED` pelo gate estrito.

Evidência: `web-large-evidence-task-postfix-replication-analysis-20261116.json`.
