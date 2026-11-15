# PIE Fase 3 — simulação offline das tarefas Blender A/B/C

Data: 2026-11-15  
Estado: `PASS`  
Modelo: nenhum  
Quota: zero  
Certificação: `NOT_CERTIFIED`

## Gate da simulação

As tarefas foram executadas contra a fixture Blender 5.3 real, via `pie_blender_query_scene`, com oráculos determinísticos independentes. Nenhuma sessão Codex foi iniciada.

| Tarefa | Consultas | Payload acumulado | Latência local | Resultado |
|---|---:|---:|---:|---|
| A — localização | 1 | 376 caracteres | 81,172 ms | PASS |
| B — filtragem | 1 | 1.263 caracteres | 38,908 ms | PASS |
| C — inventário | 4 | 5.620 caracteres | 221,656 ms | PASS |

## Oráculos

- A encontrou exatamente `PIE_Large_Cube_00`, tipo `MESH`, posição com três coordenadas e materiais.
- B encontrou os 10 objetos do prefixo `PIE_Large_Cube_0`, sem nomes duplicados, com materiais.
- C percorreu páginas `20/20/20/4`, totalizou 64 objetos e confirmou 64 nomes únicos.
- Cada consulta do cliente gerou uma única execução upstream read-only.
- O contrato `outputSchema` da ferramenta foi descoberto e validado.

## Interpretação

Este é um gate funcional para preparar o A/B, não uma certificação de tokens. Os tamanhos são caracteres serializados e não podem ser convertidos em tokens. A tarefa C demonstra o custo adicional de paginação; A e B são workloads adequados para testar consulta direcionada.

Evidência JSON: [`81-blender-selective-task-simulation.json`](81-blender-selective-task-simulation.json).

## Recomendação para o piloto

Liberar somente o primeiro par real da tarefa A, com baseline usando as ferramentas originais e optimized usando explicitamente `pie_blender_query_scene`, mesmo prompt, mesma fixture e oráculo equivalente. Interromper no primeiro erro de rota, uso ausente do provedor, chamada inesperada ou falha do oráculo. Depois avaliar B e C separadamente; não combinar os resultados como se fossem compactação transparente.
