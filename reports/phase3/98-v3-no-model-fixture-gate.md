# PIE Fase 3 — gate v3 sem modelo

`PASS_NO_MODEL_GATE`. A fixture GUI descartável do Blender 5.3 foi carregada em processo separado na porta `9878`; o Blender do usuário permaneceu em `9877`.

| Braço | Servidor | Ferramenta | Fixture | Resultado |
|---|---|---|---|---|
| Baseline | `blender` | `execute_blender_code` | objeto e material presentes | PASS |
| Optimized | `pie-blender-optimized` | `pie_blender_query_scene` | objeto e material presentes | PASS |

Ambos passaram `initialize`, `tools/list` e `tools/call`, sem sessões de modelo e sem consumo de quota. A configuração isolada tem exatamente um servidor habilitado por braço. O baseline retorna os quatro valores por código Blender read-only; o optimized retorna os mesmos valores pela consulta seletiva.

Essa evidência valida a comparabilidade funcional do cenário v3, não economia de tokens.
