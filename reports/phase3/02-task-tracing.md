# Fase 3 — rastreamento de tarefas

O ledger agora registra `task_id`, `run_id`, `application`, `tool_name`, `timestamp` UTC, `condition`, `status` e `duration_ms`, além dos contadores de caracteres e tokens reportados.

- `task_id`: vem de `PIE_TASK_ID`; valor inválido ou ausente vira `unassigned`.
- `run_id`: vem de `PIE_RUN_ID`; se ausente é gerado automaticamente como `run-<pid>`, mantendo correlação no processo sem depender de a IA inventar IDs.
- `application`: classificação determinística para Blender/Web e fallback `other_mcp`.
- `condition`: `PIE_CONDITION`, com default `observed`.
- `status`: derivado do estado da chamada, sem confundir caracteres com tokens.
- `duration_ms`: tempo medido no gateway MCP para cada resposta.

Consulta/exportação:

```powershell
uv run -m pie.certification.task_telemetry report --workspace . --app web --task-id minha-tarefa --run-id run-123 --output reports/phase3/web.json
```

Sem correlação válida, o sistema registra `unassigned`; não atribui uma chamada a uma tarefa por inferência textual.

