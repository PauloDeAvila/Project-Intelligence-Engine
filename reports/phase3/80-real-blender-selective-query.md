# PIE Fase 3 — consulta seletiva real Blender

Data: 2026-11-15  
Estado: `PASS`  
Ferramenta: `pie_blender_query_scene`  
Certificação: `NOT_CERTIFIED`

## Contrato próprio

A nova ferramenta não altera `get_scene_info`. Ela declara `inputSchema` e `outputSchema` próprios, aceita somente a intenção `find_objects`, filtros limitados (`name_prefix`/`name_contains`), campos allowlisted, `limit` de 1–100 e `offset` de 0–10000.

O retorno usa `pie-blender-query-scene-v1` e contém `items`, `total`, `offset`, `limit`, `next_offset` e `complete`. A execução interna usa uma única chamada read-only de `execute_blender_code` por consulta; nenhum código fornecido pelo modelo é encaminhado.

## Probe real

Fixture Blender 5.3 GUI descartável, mesma cena de 64 objetos e 16 materiais, porta `9877`. O probe fez quatro consultas consecutivas com prefixo `PIE_Large_Cube_` e campos `name`, `type`, `material_count`.

| Offset | Itens | Payload serializado | `next_offset` |
|---:|---:|---:|---:|
| 0 | 20 | 1.692 | 20 |
| 20 | 20 | 1.693 | 40 |
| 40 | 20 | 1.693 | 60 |
| 60 | 4 | 542 | `null` |

Oráculo: PASS. Todos os nomes têm o prefixo esperado, os campos retornam com tipos corretos e a paginação é determinística. Cada consulta de cliente gerou exatamente uma execução interna no upstream.

O payload da primeira página é aproximadamente 47,34% menor que a resposta `get_scene_info` real de 3.213 caracteres, mas essa diferença é uma comparação entre contratos diferentes e não é economia de tokens certificada.

Evidência completa: [`80-real-blender-selective-query.json`](80-real-blender-selective-query.json).

## Decisão

`pie_blender_query_scene` está pronta para um probe de contrato e para um experimento separado de capacidade seletiva. Ela não deve ser apresentada como compactação transparente de `get_scene_info`, nem usada para declarar economia antes de um A/B com tarefa, ferramentas e oráculo equivalentes.
