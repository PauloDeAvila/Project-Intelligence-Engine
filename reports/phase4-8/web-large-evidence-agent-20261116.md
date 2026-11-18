# Web grande — Evidence Agent DeepSeek

## Resultado

O agente DeepSeek escolheu os campos necessários e o código preservou os
valores diretamente da evidência MCP. Nenhum valor de página foi redigitado
pelo modelo.

- Baseline: 10.418 tokens de planejamento.
- PIE: 6.880 tokens de planejamento.
- Redução de planejamento: 33,96%.
- Oráculo da fonte: aprovado nos dois braços.
- Oráculo do plano (`title`, `status`, `marker`): aprovado nos dois braços.
- Latência: 3,3937 s → 4,2279 s.

## Escopo

Este é um experimento `planning_only`: mede a decisão do agente e a
reconstrução determinística pelo código. Não é equivalente à certificação da
tarefa completa de resposta livre, que permanece inválida nos pilotos
anteriores.

Evidência: `web-large-evidence-agent-20261116.json`.
