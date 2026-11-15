# Plano A/B Blender — tarefa A

Data: 2026-11-15  
Estado: `READY_FOR_MANUAL_PILOT`  
Execução: `PLAN_ONLY_NO_MODEL_EXECUTION`  
Certificação: `NOT_CERTIFIED`

## Escopo

Foi preparado um único par real para `blender-selective-location-v1`:

- Baseline: servidor `blender`, somente `get_scene_info`.
- Optimized: `pie-blender-optimized`, somente `pie_blender_query_scene`.
- Modelo: `gpt-5.6-luna`, esforço `medium`.
- Fixture: `large_scene_spec.json`, sem mutação.
- Pair ID: `pair-288fe55747ef4d1c84832a2d`.
- Run IDs: `baseline-a0a4660e39bd47ed9c0b738e` e `optimized-ba0d6237c3f6486c8505335c`.
- Sessões planejadas: 2.
- Retry automático: desabilitado.

O prompt é idêntico nos dois braços e exige somente um objeto JSON com os campos `object_name`, `object_type`, `location` e `material_names`; o marcador textual deixou de ser o critério de sucesso. A diferença de ferramentas é intencional e está declarada como `selective_query_product_comparison_not_transparent_compaction`.

## Oráculo

O resultado independente precisa confirmar exatamente:

```json
{"object_name":"PIE_Large_Cube_00","object_type":"MESH","location":[0.0,0.0,0.0],"material_names":["PIE_Large_Material_00"]}
```

O cenário A é de uma página; a limitação de snapshot entre páginas não afeta este primeiro par. Tarefas paginadas continuam bloqueadas para uso geral até haver snapshot-bound contract ou estado imutável garantido.

## Profiles

Profiles gerados em diretório temporário, sem credenciais ou alteração persistente:

- Baseline SHA-256: `597AA14443AD197A2F5BA63E6AA5F7B71882BD2522FB030DD9245D84FE80D76C`.
- Optimized SHA-256: `E6384723B0C5772CE262F431F62A63C4ADE5C81F6D5EFEE21B87089C403DDAFA`.

Evidência de plano: [`83-blender-selective-a-plan.json`](83-blender-selective-a-plan.json).

As allowlists estáticas agora são exatas: `enabled_tools` e as tabelas de ferramentas de cada servidor contêm somente a ferramenta esperada para o braço. Isso ainda não substitui a comprovação de runtime.

## Identidade e gate para execução manual

O `pair_id`, `attempt_nonce` e cada `run_id` são gerados por tentativa. Repreparar o plano não reutiliza a identidade anterior.

O cenário usa o mesmo contrato do controlador (`scenario_id`, `expected_mcp_tools_by_condition`); a execução pode receber os IDs congelados com `--run-id` e `--pair-id`. Os perfis apontam para o código-fonte do commit `980c99e` e o preflight compara a árvore `src/`, permitindo commits posteriores apenas de relatórios.

Só considerar uma execução válida se o handshake `tools/list` e a telemetria `tools/call` comprovarem o servidor e a ferramenta exatos, além de uso reportado pelo provedor, oráculo JSON aprovado, `run_id`/`pair_id` correspondentes e persistência SQLite. Qualquer ferramenta adicional, rota incorreta ou falha interrompe o par sem retry automático.

Probe atual sem modelo: baseline e optimized passaram `initialize`, `tools/list` e `tools/call` contra a fixture descartável de 64 objetos e 16 materiais; ambos encontraram `PIE_Large_Cube_00`. O piloto pago ainda depende do preflight final do Codex e da autorização aplicável.
