# Web Evidence Task — Replicação JSON

O runner passou a exigir `response_format: {"type":"json_object"}` depois de
uma execução sem esse contrato produzir DSML não autorizado.

- Pares válidos: 3/3.
- Tokens baseline: 23.519.
- Tokens PIE: 18.721.
- Economia ponderada: 20,401%.
- Média das economias: 20,382%.
- Faixa: 3,077 pontos percentuais.
- Oráculos: 3/3 em ambos os braços.
- Latência média: 3,8297 s → 3,5427 s, redução de 7,496%.

O resultado é consistente nesta fixture e neste provedor, mas continua sendo
evidência local, não certificação oficial Codex nem generalização para tarefas
Web arbitrárias.

Evidência: `web-large-evidence-task-jsonmode-replication-analysis-20261116.json`.
