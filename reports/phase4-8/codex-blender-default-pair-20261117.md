# Codex Blender A/B — primeiro par real

Data: 2026-11-17  
Commit: `09277f3af1d22ed78a9e14ba2d7be0629ceabd2d`  
Par: `pair-codex-blender-default-20261117`

## Resultado

O par foi válido. O Codex usou `gpt-5.6-luna` com esforço `medium`, a mesma fixture Blender 5.3 e o mesmo prompt. As duas respostas passaram pelo oráculo JSON independente e a cena permaneceu inalterada após a execução.

| Métrica | Baseline | Optimized / PIE | Variação |
|---|---:|---:|---:|
| Input tokens | 171.378 | 83.175 | 51,467% menor |
| Input cacheado | 153.728 | 75.136 | 51,124% menor |
| Input não cacheado | 17.650 | 8.039 | 54,453% menor |
| Output tokens | 835 | 681 | 18,443% menor |
| Total tokens | 172.213 | 83.856 | **51,307% menor** |
| Latência | 24.257,206 ms | 25.554,907 ms | 5,350% maior |
| Chamadas MCP | 2 | 2 | 0 |

`reasoning_output_tokens` reportados: baseline 513, optimized 452. Eles permanecem separados e não são somados novamente ao total.

## Rotas comprovadas

- Baseline: servidor `blender`; `get_addon_status` → `get_scene_info`.
- Optimized: servidor `pie-blender-optimized`; `get_addon_status` → `pie_blender_get_object`.
- Ambos os servidores tiveram status `completed`; nenhum servidor paralelo foi observado dentro dos `CODEX_HOME` temporários.
- O gateway PIE persistiu 19 eventos de ciclo de vida e 2 eventos de chamada MCP concluída no store temporário.

## Correção e integridade

Os dois oráculos passaram. A resposta optimized possui o mesmo SHA-256 esperado (`910dd17a...b5c0ca1`) e a verificação posterior encontrou a cena padrão com `Cube` em `[0.0, 0.0, 0.0]` e material `Material`.

## Veredito

`VALID_SINGLE_PAIR_NOT_CERTIFIED`.

O resultado comprova economia real de 51,307% neste cenário Blender, mas não permite declarar certificação geral: ainda faltam as repetições exigidas, os pares Web pelo executor isolado e a análise de variabilidade. O custo financeiro permanece `null` porque não há tarifa verificada para o modelo.

Evidência JSON: `reports/phase4-8/codex-blender-default-pair-20261117.json`.
