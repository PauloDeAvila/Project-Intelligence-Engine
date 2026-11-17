# Gate de replicação Blender ao vivo

O gateway PIE e o MCP Blender original foram exercitados contra a mesma cena
real do Blender 5.3.0, sem alterações. O DeepSeek 3.2 recebeu os resultados
dos dois braços e o código comparou a resposta com um oráculo exato.

- Gate local: `CERTIFIED` para esta suíte.
- Pares válidos: 3/3.
- Tokens baseline: 16.126.
- Tokens PIE: 1.044.
- Economia ponderada: 93,526%.
- Entrada não cacheada: 9.622 → 166, redução de 98,275%.
- Oráculos: 3/3 em ambos os braços.
- Chamadas MCP: 3 por braço em cada par.
- Retries: 0; duplicações: 0.
- Modelo: `gambiarraapi/deepseek-v3.2`.
- Rota otimizada: allowlist explícita de `pie_blender_get_object`.

As primeiras tentativas inválidas foram preservadas: uma expôs o catálogo
completo e estourou o limite de raciocínio; outra revelou diferença semântica
de capitalização (`mesh`/`MESH`) no oráculo. O piloto foi corrigido sem ocultar
essas falhas.

Limitações: a latência variou significativamente entre pares; o hash registrado
é do oráculo determinístico da tarefa e da identidade verificada da cena, não
um snapshot independente completo do arquivo `.blend`; portanto este resultado
é uma certificação local do protocolo e não certificação oficial do Codex.

Evidência: `blender-live-replication-gate-20261116.json`.
