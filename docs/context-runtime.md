# PIE Context Runtime

O Context Runtime reúne seis capacidades determinísticas do PIE sem depender
de um modelo específico:

| Pilar | API principal | Persistência |
| --- | --- | --- |
| State Engine | `ContextRuntime.start`, `record`, `resume`, `checkpoint` | SQLite do PIE |
| Context Compiler | `ContextRuntime.compile`, `compile_checkpoint` | Não persiste o payload compilado |
| Local Execution | `register_operation`, `execute_local` | Journal opcional, sem argumentos/resultados |
| Adaptive Runtime | `ContextRuntime.choose` | Usa somente métricas fornecidas |
| Multi-Agent Memory | `runtime.memory.checkpoint`, `restore`, `references` | Checkpoints hash-verificados |
| Continuous Certification | `evaluate_pair`, `evaluate_suite` | Evidência de uso do provedor |

## Inicialização

```python
from pathlib import Path
from pie.runtime import ContextRuntime, OperationSpec

root = Path(".").resolve()
with ContextRuntime(
    root,
    journal_path=Path(".pie") / "runtime.sqlite3",
    graph_path=Path(".pie") / "context-runtime-graph.sqlite3",
) as runtime:
    task = runtime.start("inspect the project")
    runtime.record(task["task_id"], "note", "started")
```

Os caminhos relativos são resolvidos sob `root`. O Runtime não cria journal ou
grafo quando o caminho correspondente não é informado.

## Compilação e memória

O compilador recebe caminhos obrigatórios explícitos e falha se a evidência não
couber no orçamento ou estiver ausente. O payload entregue ao modelo é apenas
`CompiledContext.model_payload()`; o envelope com hashes e caminhos deve ficar
no armazenamento local.

Checkpoints armazenam dados JSON limitados e hashes SHA-256. A memória entre
agentes expõe referências e proveniência verificáveis; não retorna o estado de
outro agente sem uma restauração explícita e validada.

## Execução local

Somente operações registradas por `OperationSpec` podem ser executadas. Os
argumentos e resultados são JSON limitados, chaves sensíveis são bloqueadas e
timeouts são cooperativos: o handler precisa consultar `ExecutionContext`.
Com journal, a mesma operação é executada uma vez; uma repetição retorna
`REPLAYED` sem reexecutar nem recuperar automaticamente o resultado privado.

## MCP

`pie_context_runtime` oferece apenas metadados read-only do Runtime:

- `graph_snapshot`
- `graph_order`
- `agent_references`
- `agents`

O banco do grafo é o caminho fixo
`.pie/context-runtime-graph.sqlite3`, aberto com SQLite `mode=ro`. A ferramenta
não cria o arquivo, não executa operações, não restaura checkpoints e não
aceita caminhos fornecidos pelo cliente. Ela fica fora do perfil MCP compacto
para não aumentar o contexto padrão.

## Certificação

`ContinuousCertification` só retorna `CERTIFIED_PAIR`/`CERTIFIED` quando as
duas execuções possuem uso do provedor disponível, tokens reais, rota
verificada, oráculo aprovado, latência e chamadas MCP. Dados ausentes permanecem
`NOT_CERTIFIED`; caracteres não são convertidos em tokens.

No estado atual, a validação local está aprovada, mas a certificação externa de
tokens permanece `NOT_CERTIFIED` porque o upstream GLM observado retornou
HTTP 429 e não forneceu um payload `usage`.

Evidências: `reports/phase3/context-runtime-pillars-validation.json` e
`reports/phase3/context-runtime-mcp-exposure.json`.
