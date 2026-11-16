# Fase 5 — handoff real entre agentes

Resultado: `PASS_EXTERNAL_CONTROLLED`.

O OpenCode executou duas chamadas reais com `infinity/deepseek-v3.2`. O agente
`deepseek-a` retornou `HANDOFF_READY`; o PIE salvou somente o estado compacto,
criou um handoff para `deepseek-b`, reiniciou o `ContextRuntime` e restaurou o
checkpoint. O segundo agente recebeu apenas esse contexto verificado e
retornou `HANDOFF_RESUMED`.

Evidências:

- `task_id`: `cbfb6b57-fe4d-4661-a64b-32d22a0120b5`.
- Versão de contexto de origem: `1`.
- Versão de contexto do receptor: `2`.
- Hash e proveniência do checkpoint verificados pelo PIE.
- Histórico completo, prompts e respostas não foram persistidos.
- Uso reportado pelo provedor está em `live-agent-handoff.json`.

Limite: este é um handoff controlado de uma tarefa mínima. Ele comprova o
contrato e a persistência, mas não certifica a qualidade geral de agentes nem
a economia oficial Codex.
