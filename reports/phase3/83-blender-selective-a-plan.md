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
- Pair ID: `pair-3b39f65ee19947a5bf55bfb5`.
- Run IDs: `baseline-dfc5c964a5184449ae59471b` e `optimized-2daf14f0c2e5435f83589c00`.
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
- Optimized SHA-256: `9AEB1478E5A60F87B0C2185D224426A67A442AFE1FEA788BD589D2398E188418`.

Evidência de plano: [`83-blender-selective-a-plan.json`](83-blender-selective-a-plan.json).

As allowlists estáticas agora são exatas: `enabled_tools` e as tabelas de ferramentas de cada servidor contêm somente a ferramenta esperada para o braço. Isso ainda não substitui a comprovação de runtime.

## Identidade e gate para execução manual

O `pair_id`, `attempt_nonce` e cada `run_id` são gerados por tentativa. Repreparar o plano não reutiliza a identidade anterior.

O cenário usa o mesmo contrato do controlador (`scenario_id`, `expected_mcp_tools_by_condition`); a execução pode receber os IDs congelados com `--run-id` e `--pair-id`. Os perfis apontam para o commit `0e84cf5`.

Só considerar uma execução válida se o handshake `tools/list` e a telemetria `tools/call` comprovarem o servidor e a ferramenta exatos, além de uso reportado pelo provedor, oráculo JSON aprovado, `run_id`/`pair_id` correspondentes e persistência SQLite. Qualquer ferramenta adicional, rota incorreta ou falha interrompe o par sem retry automático.

Probe atual sem modelo: baseline passou a chamada direta; optimized passou descoberta, mas a consulta retornou `PIE_QUERY_UNAVAILABLE` porque o Blender live não devolveu o marcador esperado. O piloto pago permanece bloqueado até a fixture ser carregada/verificada e a consulta seletiva passar.
