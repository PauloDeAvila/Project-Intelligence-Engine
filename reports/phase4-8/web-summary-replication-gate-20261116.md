# Gate de replicação Web Summary

O gate local `pie-certification-replication-v1` aprovou três pares reais do
DeepSeek 3.2 na fixture Web Summary.

- Status do gate: `CERTIFIED` para esta suíte local.
- Pares: 3/3 válidos.
- Tokens baseline: 20.502.
- Tokens PIE: 17.852.
- Economia total ponderada: 12,926%.
- Entrada não cacheada: 4.707 → 2.027, redução de 56,936%.
- Chamadas MCP: 6 por braço em todos os pares.
- Oráculos: 3/3 baseline e 3/3 PIE.
- Rotas: `upstream_mcp` e `pie_gateway`, verificadas.
- Retries automáticos: 0.
- Duplicações: 0.
- Modelo efetivo: `gambiarraapi/deepseek-v3.2`.

O gate rejeita evidência sem uso do provider, cache não observado, modelo
divergente, rota/trace MCP incompleto, retry, duplicação de `pair_id` ou
repetição do mesmo cenário/fixture/índice de replicação.

Este resultado é uma certificação local do protocolo de evidência Web Summary;
não é certificação oficial do Codex, nem generalização para Blender/Web em
geral. A diferença de cache entre braços permanece registrada nos JSONs.

Evidência: `web-summary-replication-gate-20261116.json`.
