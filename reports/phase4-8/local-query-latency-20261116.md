# Latência de consulta local indexada

Foi medida a consulta `ContextRuntime` no índice SQLite atual, em processo
único, após aquecimento e sem chamadas de modelo.

- Amostras: 100.
- Resultados por consulta: 47.
- p50: 2,8788 ms.
- p95: 3,6046 ms.
- p99: 3,8769 ms.
- Máximo: 3,9016 ms.
- Meta p95: 100 ms — aprovada.
- Chamadas de provider: 0.

Este resultado mede somente a consulta local indexada; não representa a
latência total de uma tarefa com provider, MCP ou navegador.
