# PIE Fase 3 — causa da divergência do oráculo Blender

## Causa confirmada

O fixture histórico define os valores no nó `BSDF_PRINCIPLED`, enquanto o prompt da primeira execução lia propriedades de nível `Material`:

| Campo | Material-level observado | Principled esperado/observado |
|---|---:|---:|
| roughness | `0.4000000059604645` | `0.3499999940395355` |
| metallic | `0.0` | `0.20000000298023224` |

O objeto e o material estavam corretos: `PIE_AB_Cube` e `PIE_AB_Material`. A leitura foi somente leitura e não alterou a cena.

## Correção

O cenário Blender foi atualizado para localizar o nó por `node.type == 'BSDF_PRINCIPLED'` e ler os inputs `Roughness` e `Metallic`, alinhando o prompt ao oráculo independente e às instruções do MCP para evitar nomes localizados.

Foi adicionado um teste de contrato para impedir o retorno à leitura `mat.roughness`/`mat.metallic`.

A execução `baseline-1c07733a5e3840e3ad9a9b79` permanece inválida para A/B; seu prompt hash não corresponde ao cenário corrigido. Nenhuma nova execução foi iniciada nesta correção.
