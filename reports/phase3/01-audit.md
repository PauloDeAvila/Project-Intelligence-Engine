# Fase 3 — auditoria da implementação

Data: 2026-11-14  
Branch: `feat/pie-phase3-task-telemetry-20261114`  
Base auditada: `origin/feat/pie-blender-web-domain-gateway-20261114`

## Arquitetura encontrada

- `MCPStdioGateway` encaminha JSON-RPC sem chamadas extras e compacta somente resultados textuais explicitamente elegíveis.
- `gateway.metrics` registra caracteres em `index.sqlite3`; `task_telemetry` mantém um ledger adicional na mesma base.
- `live_codex` aceita somente eventos `turn.completed` com uso reportado pelo provedor e rejeita registros incompletos, pares duplicados, modelos divergentes e falhas do oráculo.
- `web_results` mantém referências/URLs relevantes em prévias sanitizadas; Blender usa recuperação local para resultados compactados.
- O fluxo de benchmark PowerShell alterna ordem baseline/optimized e exige pelo menos três repetições.

## Problemas identificados e correções

1. O ledger não tinha `run_id`, `tool_name`, `status` nem uma condição operacional aplicável a cada chamada. Corrigido com identificação automática por processo/ambiente, fallback `unassigned` e `PIE_CONDITION`.
2. Migrações antigas poderiam falhar porque índices referenciavam colunas ainda inexistentes. Corrigido migrando colunas antes dos índices.
3. SQLite não configurava `busy_timeout`/WAL. Corrigido nos dois caminhos de persistência; falhas do ledger continuam best-effort para não interromper MCP.
4. O MCP gravava duração zero para passthrough/small. Corrigido medindo do envio do request até a resposta.
5. Não havia consulta filtrada por aplicativo, tarefa, execução ou período. Corrigido na CLI `pie-usage report`.

## Riscos e limitações

- O ledger ainda não possui chave de idempotência baseada no request ID; reprocessamento externo pode duplicar eventos.
- Falhas/timeout antes de uma resposta JSON não têm evento final específico no proxy atual.
- Tokens do provedor são por turno Codex, não são distribuídos artificialmente às chamadas MCP.
- O índice PIE conectado ao ambiente apontou para outra raiz (`contrato-de-uso-ativo-do-project`), apesar de `CURRENT`; não foi usado como evidência deste checkout. Graphify local foi construído em modo AST/code-only.

## Validação executada

- `graphify . --code-only --no-viz`: 3.337 nós, 8.617 arestas.
- `uv ... -m pytest -q`: 528 passed, 5 skipped, 133 subtests passed.
- Testes focados após a alteração: 22 passed.
- `compileall`: passou.
- `unittest discover`: 533 testes, 3 falhas em diagnósticos de processo Blender já existentes no modo unittest; pytest reproduzível passou.

Auditoria read-only da rota Codex: 3 servidores MCP ativos, 0 wrapped stdio, razão de roteamento 0.0, estado `GAPS_OR_NO_ROUTED_SERVERS`. Blender, node_repl e `pie-def7be8e70` estão `UNWRAPPED_STDIO`; o monitoramento PIE não pode ser declarado ativo no uso normal.

