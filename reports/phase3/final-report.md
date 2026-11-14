# PIE Fase 3 — relatório consolidado

## Veredito

**NOT_CERTIFIED.** Os dois gateways PIE passaram chamadas reais locais, mas a bateria A/B autorizada foi interrompida na primeira captura Blender baseline: o `CODEX_HOME` isolado não tinha `auth.json`, a captura retornou `RuntimeError` e não produziu `turn.completed.usage`. Não houve repetição automática nem números fabricados.

## Implementação

- `task_telemetry`: correlação automática por tarefa/execução, status, condição, duração, migração SQLite, WAL/busy timeout, filtros e exportação JSON.
- `gateway.metrics`: persistência concorrente configurada e integração best-effort com o ledger.
- `mcp_stdio`: duração real do request até a resposta, mantendo passthrough e recuperação existentes.
- Teste de regressão para `run_id` e `condition`.

## Validação

| Verificação | Resultado |
|---|---:|
| pytest completo | 530 passed, 5 skipped, 133 subtests |
| testes focados | 26 passed |
| compileall | passou |
| unittest discover | 533 executados; 3 falhas Blender no modo unittest |
| uso real Codex | não executado |
| Blender instalado | Blender 5.3.0; addon 5.3 ativo no probe |
| chamada Blender pelo PIE | PASS: `get_scene_info`, 46.366 ms persistidos |
| chamada Web pelo PIE | PASS: Playwright local, redução de caracteres 92.858% |
| bateria Codex A/B | interrompida após 1 falha pré-turno; 0 pares válidos |

## Certificação A/B

| Domínio | Pares válidos | Tokens baseline | Tokens optimized | Economia |
|---|---:|---:|---:|---:|
| Blender | 0 | null | null | null |
| Web | 0 | null | null | null |

Os campos permanecem `null` porque a primeira captura falhou antes de produzir uso do provedor. Caracteres economizados continuam explicitamente separados de tokens.

## Como operar o monitoramento

Os gateways existentes inicializam a instrumentação ao encaminhar chamadas. Para consultar:

```powershell
uv run -m pie.certification.task_telemetry report --workspace .
uv run -m pie.certification.task_telemetry report --workspace . --app blender --output reports/phase3/blender-live.json
```

O SQLite fica no armazenamento PIE do workspace; `PIE_GLOBAL_STORAGE_ROOT` continua opt-in. Eventos sem correlação usam `unassigned`.

A auditoria pós-ativação encontrou 5 servidores ativos, 2 rotas PIE (`pie-blender-optimized` e `pie-web-optimized`) e `configured_routing_ratio: 0.4`. Os servidores originais `blender`, `node_repl` e `pie-def7be8e70` permanecem intactos. As chamadas reais Blender e Web passaram, mas o provedor Codex não foi executado para este estágio.

## Limitações e próximos passos

1. Selecionar explicitamente os servidores PIE no fluxo normal do Codex; a preferência automática ainda não foi demonstrada.
2. Preparar dois `CODEX_HOME` explicitamente auditáveis, sem alterar credenciais do usuário.
3. Executar 3 pares por cenário/domínio com `tools/run_live_codex_pairs.ps1` e importar os registros.
4. Adicionar evento final para timeout/encerramento inesperado e idempotência por request ID.
5. Medir overhead real e só então promover o estado de certificação.

O diff, backup e rollback estão em [`07-routing-plan.md`](07-routing-plan.md). A configuração persistente contém os dois gateways; `node_repl` não foi alterado. O uso normal ainda precisa escolher `pie-blender-optimized`/`pie-web-optimized`, pois os servidores originais continuam disponíveis para baseline.
