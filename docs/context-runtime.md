# PIE Context Runtime

O Context Runtime reúne seis capacidades determinísticas do PIE sem depender
de um modelo específico:

| Pilar | API principal | Persistência |
| --- | --- | --- |
| State Engine | `ContextRuntime.start`, `record`, `resume`, `checkpoint` | SQLite do PIE |
| Context Compiler | `ContextRuntime.compile`, `compile_checkpoint` | Não persiste o payload compilado |
| Local Execution | `register_operation`, `execute_local` | Journal opcional, sem argumentos/resultados |
| Adaptive Runtime | `ContextRuntime.choose` | Usa somente métricas fornecidas; objetivos `tokens`, `latency` e `cost` |
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

## Orçamento de tokens medido

O Context Compiler aceita um `token_budget` explícito com um `token_counter`
explícito (`Callable[[str], int]`). O orçamento só é aplicado quando ambos são
fornecidos: um `token_budget` sem `token_counter` válido — ou um contador que
falhe, retorne `bool` ou inteiro negativo — falha fechado com
`token_counter_unavailable`; se a medição exceder o orçamento, a compilação
falha com `evidence_exceeds_token_budget`. Nenhum caractere é convertido em
tokens e nenhuma projeção parcial escapa.

O verificador `tools/verify_context_runtime.py` exercita esse gate usando
apenas um contador sintético não-tokenizante (`_synthetic_fixture_counter`),
que retorna uma constante independente do payload. Ele não é um tokenizador e
não mede nem estima tokens; qualquer medição real deve vir do `usage` do
provedor. O verificador relata o gate como `PASS_SYNTHETIC_COUNTER` e diz isso
explicitamente.

Checkpoints armazenam dados JSON limitados e hashes SHA-256. A memória entre
agentes expõe referências e proveniência verificáveis; não retorna o estado de
outro agente sem uma restauração explícita e validada, com caminhos
fail-closed cobertos por testes.

## Deltas Blender com histórico versionado

O `SceneDeltaCache` mantém um histórico versionado por chave `(scene, scope)`
na tabela `scene_delta_fingerprint_history`, limitado a 5 versões por chave
(DELETE de versões antigas no mesmo commit). Cada versão armazena apenas
digest, counts, estado e timestamp — nunca conteúdo de snapshot. A escrita usa
upsert (`ON CONFLICT ... DO UPDATE`) em vez de apagar linhas de outras
instâncias/processos que compartilham o mesmo store, e o histórico é anexado
com `BEGIN IMMEDIATE` para serializar escritores antes do cálculo de
`MAX(version) + 1`. Falha de persistência degrada para memória, como no resto
do cache.

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

## Evidência real do piloto GLM (3 tarefas, v5)

O piloto local GLM com 3 tarefas está registrado em
`reports/phase3/glm-real-pilot-live-v5/summary.json` e em
`reports/phase3/context-runtime-verifier-glm-v5.json`. Números observados:

- 3 tarefas, 3 corretas no baseline e 3 corretas no PIE;
- `provider_usage_status` = `ok` nos dois modos;
- baseline: prompt 17373 / completion 74 / total 17447 tokens, cached 0;
- PIE: prompt 1877 / completion 64 / total 1941 tokens, cached 0;
- economia de input: 89.196%; economia total: 88.875%;
- latência mediana: baseline 2.5571 s, PIE 2.8329 s.

A execução v4 anterior é uma falha preservada: 2/3 corretas no modo PIE por
símbolo entre colchetes. A correção (preservação da evidência exata de
símbolo) está no commit `8cc6706`
(fix(benchmark): preserve exact symbol evidence).

## Correção Web de snapshots pequenos

O filtro Web não rejeita mais snapshots locais válidos apenas por terem menos
de 500 caracteres. O commit `f8e8788` usa um envelope estrutural mínimo de 80
caracteres e preserva os demais gates: marcador, role/ref, allowlist,
redaction, rejeição de segredos/erros e limite superior de 500.000 caracteres.
Os 12 testes específicos e 47 testes de regressão passaram. A execução MCP
real desta sessão ainda não é evidência do checkout atual porque o servidor
PIE ativo reportou outra raiz; o detalhe está em
`reports/phase3/context-runtime-web-live-probe-20261116.json`.

## Certificação

`ContinuousCertification` só retorna `CERTIFIED_PAIR`/`CERTIFIED` quando as
duas execuções possuem uso do provedor disponível, tokens reais, rota
verificada, oráculo aprovado, latência e chamadas MCP. Dados ausentes permanecem
`NOT_CERTIFIED`; caracteres não são convertidos em tokens.

O objetivo `cost` do Adaptive Runtime exige um `cost_usd` explícito, finito e
não negativo, acompanhado de uso do provedor disponível. Sem tarifa ou uso
verificados, o candidato é inelegível; o PIE não estima preço a partir de
caracteres ou de limites de assinatura.

No estado atual, a validação local está aprovada. O piloto GLM local mais
recente de 3 tarefas (v5) reportou uso real do provedor
(`reports/phase3/context-runtime-verifier-glm-v5.json`, evidência
`PILOT_VALID`, 3/3 corretas em baseline e PIE, `provider_usage_status` `ok`,
economia de input 89.196% e total 88.875%, cached 0 nos dois modos), mas é
complementar: não constitui a certificação Codex nem a bateria pareada
Blender/Web e não eleva o status acima de `NOT_CERTIFIED`. Sondas anteriores
com HTTP 429 permanecem registradas como histórico negativo, não como
evidência positiva.

## Guardas fail-closed após o fechamento

O `ContextRuntime` mantém guarda fail-closed após `close()`: o acesso à facade
`memory` e os métodos que tocam estado de memória ou checkpoints
(`checkpoint`, `checkpoint_agent`, `restore_state`, `list_agent_checkpoints`)
levantam `RuntimeError` quando o runtime já está fechado. O `close()` também
fecha o grafo e o journal de forma tolerante a falha individual, zera as
referências (incluindo `memory`) e repropaga o primeiro erro após liberar todos
os recursos. Esses contratos e os contratos da facade (compilação com
`token_budget` exigindo `token_counter`, execução local sem journal sem replay,
round-trip de `restore_state` e snapshots do grafo com/sem tarefas) têm
cobertura dedicada em `tests/test_context_runtime.py`.

## Histórico recente

Commits que introduziram estes comportamentos:

- `ca8d343` test(runtime): cover multi-agent memory fail-closed paths
- `a9f92af` feat(runtime): enforce measured context token budgets
- `b087093` test(runtime): verify token budget gates fail closed
- `f004fc0` docs(runtime): record token budget homologation
- `bdab33f` feat(blender): persist versioned delta history safely
- `fa45fa6` fix(runtime): fail closed after context shutdown
- `8bee2c1` test(runtime): cover facade contracts and budgets
- `8cc6706` fix(benchmark): preserve exact symbol evidence
- `f8e8788` fix(web): accept bounded structural snapshots

Evidências: `reports/phase3/context-runtime-pillars-validation.json`,
`reports/phase3/context-runtime-mcp-exposure.json`,
`reports/phase3/context-runtime-verifier-glm-v5.json` e
`reports/phase3/glm-real-pilot-live-v5/summary.json`.
