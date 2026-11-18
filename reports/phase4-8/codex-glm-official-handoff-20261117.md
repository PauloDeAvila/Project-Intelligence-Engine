# Handoff oficial Codex → GLM

O Codex `gpt-5.6-luna` iniciou uma tarefa pelo servidor temporário
`pie_runtime` apontado para o checkout correto e registrou um checkpoint
`completed` por `pie_task_record`. O `config.toml` persistente não foi alterado.

O registro foi restaurado localmente pelo PIE e somente o checkpoint compilado
foi enviado ao GLM `gambiarraapi/glm-5.3-flash` via OpenCode/Infinity. O GLM
confirmou `handoff_state=received`, o mesmo `task_id`, o objetivo e o fato
verificado, com `history_received=false`.

Uso reportado:

- Codex: 130.514 entrada, 113.536 cacheados, 592 saída e 255 reasoning.
- GLM: 6.366 entrada, 229 cacheados, 68 saída e nenhum reasoning reportado.

O oráculo passou: Codex criou o checkpoint, o PIE o restaurou, o GLM recebeu o
conteúdo mínimo e o histórico completo não foi enviado. Esta é uma prova
controlada de handoff, não uma certificação estatística de tarefas múltiplas.

Evidência estruturada: `codex-glm-official-handoff-20261117.json`.
