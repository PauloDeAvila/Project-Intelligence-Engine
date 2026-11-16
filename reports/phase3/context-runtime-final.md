# PIE Context Runtime — validação da implementação

Data da validação: 16/11/2026

## Veredito

`IMPLEMENTED_AND_LOCALLY_VALIDATED`; certificação de tokens externos:
`NOT_CERTIFIED`.

O runtime foi exercitado localmente sem rede e a suíte completa passou. Isso
comprova contratos, persistência, limites e integração entre os seis pilares;
não comprova economia de tokens de um provedor quando não existe um payload
`usage` verificável.

## Matriz de evidências

| Pilar | Evidência atual | Estado |
| --- | --- | --- |
| State Engine | `ContextRuntime.start`, `record`, `resume`, checkpoints e restauração hash-verificada | PASS local |
| Context Compiler | projeção por caminhos obrigatórios, `token_budget`/`token_counter` explícitos com falha fechada e SHA-256 | PASS local |
| Local Execution | allowlist, JSON limitado, timeout cooperativo e replay idempotente | PASS local |
| Adaptive Runtime | seleção por tokens, latência e `cost_usd` explícito; qualidade obrigatória | PASS local |
| Multi-Agent Memory | checkpoints por agente, proveniência e referências sem payload de estado | PASS local |
| Continuous Certification | avaliador pareado fail-closed para tokens, rota, oráculo, latência e chamadas | PASS local / uso externo pendente |

O adaptador `pie.certification.provider_usage` normaliza respostas
OpenAI-compatíveis, incluindo cache e reasoning, e deixa o status
`unavailable` quando qualquer campo obrigatório não é reportado.

Componentes complementares já cobertos pelo projeto: deltas Blender/Web,
recuperação paginada de outputs, hashes de proveniência e grafo de tarefas.
Eles permanecem sujeitos aos mesmos limites e não substituem tokens reais.

## Orçamento de tokens e deltas versionados

O Context Compiler agora exige `token_counter` explícito sempre que um
`token_budget` é fornecido. Sem contador válido, ou com contador que falhe ou
retorne valor inválido, a compilação falha com `token_counter_unavailable`;
medição acima do orçamento falha com `evidence_exceeds_token_budget`. Nenhum
número de caracteres é convertido em tokens.

O verificador usa somente um contador sintético não-tokenizante (constante,
independente do payload) e reporta o gate como `PASS_SYNTHETIC_COUNTER`; ele
não mede nem estima tokens e diz isso explicitamente no resultado.

O `SceneDeltaCache` persiste histórico versionado por chave `(scene, scope)`
limitado a 5 versões, contendo apenas digest, counts, estado e timestamp, com
upsert e `BEGIN IMMEDIATE` para serializar escritores.

Commits que entregaram esses comportamentos: `ca8d343`, `a9f92af`, `b087093`,
`f004fc0`, `bdab33f`.

## Integração MCP

`pie_context_runtime` expõe somente:

- `graph_snapshot`;
- `graph_order`;
- `agent_references`;
- `agents`.

O banco do grafo é aberto com SQLite `mode=ro`; a ferramenta não cria o banco,
não aceita caminhos do cliente, não executa operações e não restaura estado.
Ela não aparece no perfil MCP compacto.

## Comandos reproduzíveis

```powershell
$env:PYTHONPATH="$(Get-Location);$(Join-Path (Get-Location) 'src')"
uv run --with pytest python -m pytest -q
uv run python -m compileall -q src/pie tests
uv build --wheel --out-dir "$env:TEMP\pie-wheel-check-context-runtime-final"
uv run python tools/verify_context_runtime.py --output reports/phase3/context-runtime-verifier.json
uv run pie status --root .
```

Resultado observado:

```text
653 passed, 4 skipped, 126 subtests passed
PIE index_state=CURRENT
workspace_match=true
verifier status=PASS_LOCAL
verifier certification=NOT_CERTIFIED
```

## Limitações honestas

O relay local GLM está operacional no checkout de trabalho e uma execução local
de um par reportou uso real do provedor (`gambiarraapi/glm-5.3-flash`). Essa
evidência é limitada a um par e ao harness local; não é a bateria Codex
pareada de Blender e Web. Por isso, ela permanece complementar e a
certificação externa continua `NOT_CERTIFIED`. Nenhum número de caracteres foi
convertido em tokens.

O relatório local do par é `reports/phase3/context-runtime-verifier-glm-v2-after-cache.json`.
As sondas anteriores que retornaram HTTP 429 permanecem registradas como
falhas históricas e não são usadas como evidência positiva.

Evidências JSON:

- `reports/phase3/context-runtime-pillars-validation.json`;
- `reports/phase3/context-runtime-mcp-exposure.json`;
- `reports/phase3/glm-provider-preflight.json`.
