# PIE Fase 3 — baseline Blender v2

## Resultado

`BASELINE_BLENDER_FAILED` por divergência de representação do tipo do objeto no oráculo. A sessão foi roteada corretamente e não houve retry nem execução do braço optimized.

| Campo | Evidência |
|---|---:|
| Modelo | `gpt-5.6-luna` |
| Input | 45.355 |
| Input cacheado | 39.680 |
| Output | 489 |
| Reasoning informado | 299 |
| Latência | 15.598,589 ms |
| Chamadas MCP | 1 |
| Rota | `blender/get_scene_info`, verificada |
| Quota | consumida |

## Diagnóstico

A resposta tinha JSON válido, exatamente as quatro chaves esperadas e tipos corretos: `object_name`, `object_type`, `location` e `material_names`. A comparação falhou porque a resposta textual do MCP original usa `"mesh"`, enquanto a fixture/oráculo usa o enum Blender `"MESH"`.

Uma sonda local sem modelo confirmou que nome, coordenadas e material correspondem à fixture. A correção aplicada normaliza apenas `object_type` para maiúsculas durante a avaliação do oráculo; não estima tokens, não altera a resposta recebida e não relaxa os demais campos.

O resultado continua inelegível para A/B: o braço optimized não foi executado e não há economia calculável.

## Evidências

- JSON bruto: `94-blender-v2-baseline.json`
- Commit da execução: `5433551aae2dd73426d350a1e91214f874932cc9`
- Rota: exatamente uma chamada `blender/get_scene_info`
- Teste da correção: `tests/test_pie_live_certification.py`
