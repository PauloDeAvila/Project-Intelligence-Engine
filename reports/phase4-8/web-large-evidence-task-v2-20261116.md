# Web Evidence Task — DeepSeek 3.2

## Resultado

O agente executou uma tarefa controlada ponta a ponta: o DeepSeek escolheu a
ação e a referência do botão, o MCP real executou a navegação e o clique, e o
código preservou os valores da fonte sem pedir ao modelo que os redigitasse.

- Baseline: 7.612 tokens.
- PIE: 5.966 tokens.
- Economia total: 21,624%.
- Oráculo da tarefa: aprovado nos dois braços.
- Latência: 3,328 s → 2,3249 s.
- Chamadas MCP: quatro por braço.

## Correções observadas durante o piloto

Uma tentativa falhou pelo limite de saída do modelo e outra revelou que o
snapshot compactado posterior não repetia o título. Ambas foram preservadas.
O runner passou a combinar as evidências de navegação, snapshot anterior e
snapshot posterior antes de avaliar o resultado.

## Limitações

É um único par local com `gambiarraapi/deepseek-v3.2`; não é certificação
oficial do Codex nem prova estatística de generalização. A execução do MCP e a
reconstrução dos valores são determinísticas e ficam fora da saída textual do
modelo.

Evidência: `web-large-evidence-task-v2-20261116.json`.
