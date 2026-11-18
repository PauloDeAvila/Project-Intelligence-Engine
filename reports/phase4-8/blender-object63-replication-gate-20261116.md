# Blender — tarefa do objeto `PIE_Large_Cube_63`

Foram executados três pares reais baseline/PIE usando a mesma cena Blender 5.3.0
e um alvo diferente do cenário principal.

- Oráculo: aprovado nos dois braços.
- Tokens agregados: 15.979 → 837.
- Economia total ponderada: 94,762%.
- Entrada não cacheada agregada: 10.183 → 184 tokens.
- Economia de entrada não cacheada: 98,193%.
- Chamadas MCP: 3 por braço.
- Oráculos: 3/3 em ambos os braços.
- Rota PIE: allowlist `pie_blender_get_object`.
- Retries: 0.
- Latência média: 3,4557 s → 1,8092 s; faixa PIE: 1,5965–2,1859 s.

Este é um gate estrito certificado para a suíte local de três repetições. Não
deve ser interpretado como certificação oficial do Codex, nem como generalização
estatística para outros objetos ou tarefas.

Evidência: `blender-object63-replication-gate-20261116.json`.
