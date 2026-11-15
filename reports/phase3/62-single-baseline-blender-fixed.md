# PIE Fase 3 — baseline Blender corrigida e válida

## Resultado

`BASELINE_BLENDER_VALID`

Esta execução usa o cenário corrigido, que lê os inputs do nó `BSDF_PRINCIPLED`. Foi uma única sessão real, sem retry; Web e optimized não foram iniciados.

| Campo | Valor |
|---|---|
| Modelo / esforço | `gpt-5.6-luna` / `medium` |
| Condição / servidor | `baseline` / `blender` |
| Cenário | `blender-material-cert-v1` |
| Workspace commit | `a95760a9ca0ef53088ae6b2375d9b9571fd3a12b` |
| `run_id` | `baseline-f073f14415ad490fa15490ef` |
| `pair_id` | `pair-deda0256ba284175ade5d58d` |
| Estado | exit code `0` |
| Latência | `17.451,210 ms` |
| Chamadas MCP | `2` |
| Oráculo textual | PASS |
| Oráculo Blender independente | PASS |

## Tokens reportados

| Métrica | Tokens |
|---|---:|
| Entrada | 58.889 |
| Cache | 35.840 |
| Entrada sem cache | 23.049 |
| Saída | 685 |
| Reasoning informado | 209 |
| Total (`input + output`) | 59.574 |

Reasoning não foi somado novamente ao total.

## Ferramentas e oráculo

As únicas chamadas observadas foram:

1. `blender/get_scene_info/completed`
2. `blender/execute_blender_code/completed`

Leitura independente read-only no Blender confirmou:

```json
{"object":"PIE_AB_Cube","material":"PIE_AB_Material","roughness":0.3499999940395355,"metallic":0.20000000298023224}
```

Nenhuma alteração foi feita na cena.

## Evidências

- Resultado: `62-single-baseline-blender-fixed-result.json`.
- Registro com usage: `62-single-baseline-blender-fixed-result-record.json`.
- Ledger: `62-single-baseline-blender-fixed-result-budget-ledger.json`, `completed`, 1/1 sessão consumida, retry false.
- Sumário: `62-single-baseline-blender-fixed-summary.json`.
- Captura forense: `C:\Users\phsra\AppData\Local\Temp\.pie-phase3-single-blender-fixed-d23a211ad98c4f7cb2bafc0f7006882c-pie-live-store\runs\baseline-f073f14415ad490fa15490ef\`.

## Próximo gate

Preservar este baseline e executar somente o braço optimized do mesmo `pair_id`, usando o mesmo commit, tarefa, modelo, esforço, fixture e oráculo. A certificação geral continua `NOT_CERTIFIED` até existir o braço optimized e os pares mínimos exigidos.
