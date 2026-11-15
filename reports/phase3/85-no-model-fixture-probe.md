# Probe sem modelo com fixture Blender

Estado: `PASS_OFFLINE_MODEL_GATE`  
Sessões de modelo: `0`  
Quota consumida: `0`

A fixture descartável foi gerada com 64 objetos e 16 materiais e carregada em uma instância GUI isolada do Blender 5.3 na porta 9877.

| Perfil | tools/list | tools/call | Ferramenta | Fixture | Ferramentas anunciadas |
|---|---|---|---|---|---:|
| Baseline | PASS | PASS | `get_scene_info` | `PIE_Large_Cube_00` encontrado | 10 |
| Optimized | PASS | PASS | `pie_blender_query_scene` | `PIE_Large_Cube_00` encontrado | 1 |

Ambos retornaram `structuredContent`. Uma chamada proibida a `get_scene_info` no gateway optimized foi rejeitada com `PIE_TOOL_NOT_EXPOSED` sem alcançar o upstream. Os perfis foram gerados contra o SHA completo `02e1b4835d2bdcee34812d4effccf7c0e1b4a4ca`.

Este gate comprova integração MCP sem modelo, não tokens, latência de sessão Codex ou economia A/B.
