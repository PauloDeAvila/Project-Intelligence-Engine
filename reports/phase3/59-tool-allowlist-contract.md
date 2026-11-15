# PIE Fase 3 — contrato de allowlist de ferramentas

## Resultado

`OFFLINE_READY_FOR_CONTROLLED_PROBE`; certificação continua `NOT_CERTIFIED`.

Os cenários agora declaram explicitamente as ferramentas MCP permitidas e esperadas, na ordem em que devem aparecer:

- Blender: `get_scene_info`, `execute_blender_code`.
- Web: `browser_navigate`, `browser_snapshot`.

O executor valida servidor, estado concluído, nomes e ordem exata. Ferramentas extras, ausentes ou fora de ordem produzem `INVALID_TOOL_ALLOWLIST` e não são certificáveis.

## Evidências

- Teste positivo e negativo da allowlist: `tests/test_pie_forensic_capture.py`.
- Cenários: `benchmarks/phase3/blender-certification-scenario.json` e `web-certification-scenario.json`.
- Índice PIE: `CURRENT`, `workspace_match=true`, sem diagnósticos.
- Suíte: `563` testes aprovados, `5` ignorados.
- Nenhuma sessão Codex iniciada e nenhum token consumido nesta etapa.

O próximo passo autorizado tecnicamente é uma única sonda real, usando os perfis corrigidos, para verificar dispatch, approval, artefatos forenses, oráculo e usage do provedor. A/B permanece bloqueado até essa sonda passar.
