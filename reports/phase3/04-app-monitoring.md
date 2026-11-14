# Fase 3 — monitoramento por aplicativo

## Blender

O proxy cobre ferramentas de cena/material configuradas para compactação e mantém recuperação sanitizada por `output_id`. Mede caracteres fonte/devolvidos, estado, ferramenta e duração. Blender 5.3.0 foi localizado fora do PATH, o addon 5.3 foi instalado/atualizado e a chamada real `get_scene_info` passou pelo gateway otimizado.

## Web / Playwright

O perfil `web` usa `web_result_eligible` e `web_snapshot_preview`, preservando referências e URLs relevantes quando presentes. A página local determinística foi navegada pelo `@playwright/mcp@0.0.85` através do gateway: 17.585 caracteres de origem, 1.256 caracteres na visão compactada, recuperação de referências e estado PASS. Isso é economia de caracteres, não tokens.

## Persistência e operação

- SQLite local com WAL, `busy_timeout=5000`, índices por tarefa/execução/data.
- Retenção: ledger de tarefa até 100.000 linhas; métricas legadas até 1.000 linhas.
- Monitoramento é instrumentação local e best-effort; uma falha de persistência não interrompe uma chamada MCP funcional.
- Exportação JSON via `pie-usage report --output`; filtros por app, task, run e intervalo ISO UTC.
- Chamadas sem resposta JSON final agora recebem evento `TIMEOUT`. A reprodução inicial foi causada pelo probe mantendo `stderr` do upstream sem drenagem; após a correção, a execução válida Blender foi `task_id=phase3-blender-live`, `run_id=run-blender-live-validated`, ferramenta `get_scene_info`, condição `optimized`, estado `PASS`, duração persistida de `46.366 ms`, 284 caracteres. Tokens permanecem `null`.

