# Plano A/B Blender — tarefa A

Data: 2026-11-15  
Estado: `READY_FOR_MANUAL_PILOT`  
Execução: `PLAN_ONLY_NO_MODEL_EXECUTION`  
Certificação: `NOT_CERTIFIED`

## Escopo

Foi preparado um único par real para `blender-selective-location-v1`:

- Baseline: servidor `blender`, ferramenta esperada `get_scene_info`.
- Optimized: `pie-blender-optimized`, somente `pie_blender_query_scene` exposta pelo gateway.
- Modelo: `gpt-5.6-luna`, esforço `medium`.
- Fixture: `large_scene_spec.json`, sem mutação.
- Pair ID: `pair-6edbe9ff6df67c85272ebc63`.
- Sessões planejadas: 2.
- Retry automático: desabilitado.

O prompt é idêntico nos dois braços. A diferença de ferramentas é intencional e está declarada como `selective_query_product_comparison_not_transparent_compaction`.

## Oráculo

O resultado independente precisa confirmar exatamente:

```json
{
  "object_name": "PIE_Large_Cube_00",
  "object_type": "MESH",
  "location": [0.0, 0.0, 0.0],
  "material_names": ["PIE_Large_Material_00"]
}
```

O cenário A é de uma página; a limitação de snapshot entre páginas não afeta este primeiro par. Tarefas paginadas continuam bloqueadas para uso geral até haver snapshot-bound contract ou estado imutável garantido.

## Profiles

Profiles gerados em diretório temporário, sem credenciais ou alteração persistente:

- Baseline SHA-256: `A411CAA65D5D7C54727D71249ABEF4CA3F2CCE7E175DA370848B4FAAB7079B69`.
- Optimized SHA-256: `D13032BEBB8035D27BAB3EADC301BEDA8882F2839891F79F7158136397CB51A6`.

Evidência de plano: [`83-blender-selective-a-plan.json`](83-blender-selective-a-plan.json).

## Gate para execução manual

Só considerar uma execução válida se houver uso reportado pelo provedor, rota exata, ferramenta esperada, oráculo aprovado, `run_id`/`pair_id` correspondentes e persistência SQLite. Qualquer falha interrompe o par sem retry automático.
