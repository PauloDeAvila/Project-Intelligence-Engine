# PIE Fase 3 — baseline Blender v2 (incidente de upstream)

## Resultado

`BASELINE_BLENDER_FAILED_ORACLE`. A chamada real foi roteada corretamente para exatamente uma ferramenta (`blender/get_scene_info`) e o provedor reportou uso real, mas o retorno continha campos nulos para a fixture. O braço optimized foi interrompido e não houve retry.

| Métrica | Valor |
|---|---:|
| Input | 45.399 |
| Cache | 39.680 |
| Output | 814 |
| Reasoning | 651 |
| Latência | 22.659,152 ms |
| Chamadas MCP | 1 |
| Rota | `VALID` |
| Quota | consumida |

## Causa identificada

O perfil foi regenerado com `BlenderPort=0`, omitindo a porta explícita `9877` usada pelo perfil validado anteriormente. O transporte MCP completou, mas não retornou os valores da fixture: `object_name` e `object_type` eram `None`, com arrays vazios.

Isso não é evidência de falha do gateway nem de economia. É um incidente de configuração do upstream. O próximo passo seguro é regenerar o perfil com `--port 9877` e repetir somente o gate sem modelo; nenhuma nova sessão Codex deve ser iniciada até esse gate passar.

Evidência forense: `C:\Users\phsra\AppData\Local\Temp\.pie-phase3-ed0449f-pie-live-store\runs\baseline-5eb2e10e0d0a23b39beb4bec`.
