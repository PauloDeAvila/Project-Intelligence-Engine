# Fase 3 — regressão e monitoramento pós-certificação

O monitoramento permanente está implementado nos gateways registrados e usa SQLite local, WAL, `busy_timeout`, retenção configurável e filtros por aplicação/tarefa/execução/período.

Ainda não há baseline histórico de tokens do provedor. Portanto, regressões de consumo de tokens não podem ser detectadas. Já existem evidências locais de chamadas Blender/Web e testes de timeout, deduplicação, persistência e passthrough.

Para liberar regressão de economia será necessário primeiro obter pelo menos três pares válidos por domínio. Qualquer nova bateria consumidora de quota exigirá autorização independente.
