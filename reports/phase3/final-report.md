# PIE Fase 3 — relatório consolidado

## Veredito

**NOT_CERTIFIED.** A instrumentação foi implementada e validada localmente, mas a certificação exige medições reais pareadas. Não há números de tokens, economia, latência ou custo a apresentar sem fabricar evidências.

## Implementação

- `task_telemetry`: correlação automática por tarefa/execução, status, condição, duração, migração SQLite, WAL/busy timeout, filtros e exportação JSON.
- `gateway.metrics`: persistência concorrente configurada e integração best-effort com o ledger.
- `mcp_stdio`: duração real do request até a resposta, mantendo passthrough e recuperação existentes.
- Teste de regressão para `run_id` e `condition`.

## Validação

| Verificação | Resultado |
|---|---:|
| pytest completo | 528 passed, 5 skipped, 133 subtests |
| testes focados | 22 passed |
| compileall | passou |
| unittest discover | 533 executados; 3 falhas Blender no modo unittest |
| uso real Codex | não executado |
| Blender instalado | não |

## Certificação A/B

| Domínio | Pares válidos | Tokens baseline | Tokens optimized | Economia |
|---|---:|---:|---:|---:|
| Blender | 0 | null | null | null |
| Web | 0 | null | null | null |

Os campos permanecem `null` porque o provedor não foi executado. Caracteres economizados continuam explicitamente separados de tokens.

## Como operar o monitoramento

Os gateways existentes inicializam a instrumentação ao encaminhar chamadas. Para consultar:

```powershell
uv run -m pie.certification.task_telemetry report --workspace .
uv run -m pie.certification.task_telemetry report --workspace . --app blender --output reports/phase3/blender-live.json
```

O SQLite fica no armazenamento PIE do workspace; `PIE_GLOBAL_STORAGE_ROOT` continua opt-in. Eventos sem correlação usam `unassigned`.

## Limitações e próximos passos

1. Instalar/disponibilizar Blender e uma página Playwright local determinística.
2. Preparar dois `CODEX_HOME` explicitamente auditáveis, sem alterar credenciais do usuário.
3. Executar 3 pares por cenário/domínio com `tools/run_live_codex_pairs.ps1` e importar os registros.
4. Adicionar evento final para timeout/encerramento inesperado e idempotência por request ID.
5. Medir overhead real e só então promover o estado de certificação.
