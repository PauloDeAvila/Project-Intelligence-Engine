# Web Evidence Task — Replicação

Foram planejados três pares DeepSeek, sem retry automático e com interrupção na
primeira falha.

- R1: válido, 7.612 → 5.966 tokens, 21,624% de economia, oráculos aprovados.
- R2: inválido; o braço PIE emitiu uma chamada DSML `browser_click` em vez do
  JSON de plano exigido. Seus tokens foram excluídos.
- R3: não executado por causa do gate de parada.

Estado: `PILOT_PARTIAL_NOT_CERTIFIED`. O caminho ponta a ponta funciona, mas a
reprodutibilidade do formato de saída do provedor ainda precisa ser resolvida.

Evidência: `web-large-evidence-task-replication-analysis-20261116.json`.
