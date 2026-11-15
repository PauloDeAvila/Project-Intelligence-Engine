# Fase 3 — Gate de evidência de rota MCP

## Resultado

O comparador A/B agora é fail-closed para roteamento. Uma execução só pode entrar na comparação quando:

- o provedor reporta uso real;
- existe pelo menos um `mcp_tool_call` persistido;
- o servidor observado corresponde ao servidor esperado da condição;
- o status de cada chamada é `completed`;
- o oráculo de correção passa.

Registros históricos sem `mcp_tools` são rejeitados e não podem ser reutilizados como certificação causal.

## Alterações

- `capture_codex` deriva o servidor esperado por domínio/condição e bloqueia capturas sem rota MCP.
- `_record` valida `expected_mcp_server`, `mcp_route_verified` e cada chamada MCP.
- Fixtures unitários foram atualizados para refletir o contrato real.

## Validação

- Teste direcionado: `10 passed, 7 subtests passed`.
- Suíte completa: `537 passed, 5 skipped, 133 subtests passed`.
- `uv run python -m compileall -q src`: PASS.
- `git diff --check`: PASS.

## Limitações e veredito

Este gate melhora a validade da próxima bateria, mas não executa benchmark nem cria tokens. A auditoria histórica continua com rota incompleta, e a certificação permanece `NOT_CERTIFIED` até 12 sessões atuais pareadas com evidência de rota, uso do provedor e oráculo aprovado.

PIE desta sessão não foi usado como evidência do checkout: o servidor disponível aponta para outra raiz. A análise estrutural foi feita pelo Graphify local (`graphify-out/graph.json`, 3394 nós / 8748 arestas).

Commit da implementação: `d2f574d926599550b4c1a22ceb98dd740b33b724`.
