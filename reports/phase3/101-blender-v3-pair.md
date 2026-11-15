# PIE Fase 3 — primeiro par Blender v3

## Resultado

Par real válido, mas amostra única: `REAL_PROVIDER_TOKENS_COMPARED`. O baseline usou `blender/execute_blender_code`; o optimized usou `pie-blender-optimized/pie_blender_query_scene`. Ambos passaram o oráculo JSON exato e o roteamento.

| Métrica | Baseline | Optimized | Variação |
|---|---:|---:|---:|
| Input | 44.726 | 44.554 | 0,385% economia |
| Input cacheado | 39.040 | 39.040 | 0 |
| Input não cacheado | 5.686 | 5.514 | 3,024% economia |
| Output | 593 | 321 | 45,868% economia |
| Total | 45.319 | 44.875 | **0,980% economia** |
| Latência | 18.378,347 ms | 13.446,835 ms | 4.931,512 ms menor |
| Chamadas MCP | 1 | 1 | sem variação |
| Oráculo | PASS | PASS | — |

Custos permanecem `null`: não há tarifa verificável para `gpt-5.6-luna`.

## Limitação

Este é somente o primeiro par válido do cenário v3. Não sustenta `CERTIFIED`; são necessários os pares restantes definidos no protocolo. A comparação mede consulta seletiva como capacidade de produto, não compactação transparente da mesma ferramenta.

Evidências: `99-blender-v3-baseline.json`, `100-blender-v3-optimized.json` e `101-blender-v3-pair.json`.
