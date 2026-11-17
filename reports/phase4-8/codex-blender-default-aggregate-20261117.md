# Codex Blender — agregado parcial

O cenário possui dois pares válidos e uma tentativa inválida. A terceira repetição foi interrompida no baseline porque o Codex chamou `get_scene_info` duas vezes; o braço optimized não foi iniciado.

| Repetição | Estado | Baseline total | Optimized total | Economia |
|---:|---|---:|---:|---:|
| 1 | válida | 172.213 | 83.856 | 51,307% |
| 2 | válida | 67.024 | 48.958 | 26,955% |
| 3 | inválida | 83.450 | não executado | não calculada |

Nos dois pares válidos, o agregado foi:

- Input: `237.770` → `131.616` tokens, economia de `44,646%`.
- Input não cacheado: `33.866` → `14.752`, economia de `56,440%`.
- Output: `1.467` → `1.198`, economia de `18,337%`.
- Total: `239.237` → `132.814`, economia de **`44,484%`**.
- Latência média: `20.871,991 ms` → `22.784,844 ms`, optimized `9,165%` mais lento.
- Chamadas MCP: `4` → `4`.

Todos os quatro oráculos válidos passaram. O resultado permanece `NOT_CERTIFIED`: a amostra planejada de três pares não foi completada e a falha de R3 exige investigação antes de novo consumo de quota.

Evidências: `codex-blender-default-pair-20261117.json`, `codex-blender-default-r2-20261117.json` e `codex-blender-default-r3-invalid-20261117.json`.
