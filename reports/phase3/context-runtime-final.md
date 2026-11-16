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
| Context Compiler | projeção por caminhos obrigatórios, orçamento e SHA-256 | PASS local |
| Local Execution | allowlist, JSON limitado, timeout cooperativo e replay idempotente | PASS local |
| Adaptive Runtime | seleção por tokens, latência e `cost_usd` explícito; qualidade obrigatória | PASS local |
| Multi-Agent Memory | checkpoints por agente, proveniência e referências sem payload de estado | PASS local |
| Continuous Certification | avaliador pareado fail-closed para tokens, rota, oráculo, latência e chamadas | PASS local / uso externo pendente |

Componentes complementares já cobertos pelo projeto: deltas Blender/Web,
recuperação paginada de outputs, hashes de proveniência e grafo de tarefas.
Eles permanecem sujeitos aos mesmos limites e não substituem tokens reais.

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
507 passed, 4 skipped, 126 subtests passed
PIE index_state=CURRENT
workspace_match=true
verifier status=PASS_LOCAL
verifier certification=NOT_CERTIFIED
```

## Limitações honestas

O relay local GLM foi sondado novamente com `gambiarraapi/glm-5.3-flash` após
o cooldown das chaves e expirou após 45075 ms, sem resposta nem `usage`. A
sonda anterior expirou após 60043 ms e o upstream anterior retornou HTTP 429.
Portanto não há certificação real de tokens, economia ou custo para essas
sondas, e nenhum número de caracteres foi convertido em tokens.

Evidências JSON:

- `reports/phase3/context-runtime-pillars-validation.json`;
- `reports/phase3/context-runtime-mcp-exposure.json`;
- `reports/phase3/glm-provider-preflight.json`.
