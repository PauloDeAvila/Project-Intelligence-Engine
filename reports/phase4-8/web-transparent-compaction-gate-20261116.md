# Gate Web — compactação transparente sem ferramenta extra

## Resultado

O gateway Web real passou `initialize` e `tools/list` usando
`@playwright/mcp@0.0.85`.

- 26 ferramentas anunciadas;
- `pie_gateway_output_get`: presente;
- `pie_web_context`: ausente por padrão;
- snapshot da fixture: 415 caracteres;
- orçamento do gateway: 2.400 caracteres.

A alteração torna `pie_web_context` opt-in. A rota padrão continua usando a
compactação transparente de `browser_snapshot` quando a observação excede o
orçamento, sem adicionar uma chamada de consulta ao modelo.

## Validação

- Testes focados: 20 aprovados.
- Suíte completa: 712 aprovados, 4 ignorados, 126 subtestes.
- Índice PIE: `CURRENT`, `workspace_match=true`.

## Limitação

A fixture Web atual é pequena e não acionou compactação neste probe. Este gate
comprova o contrato de roteamento e o isolamento da ferramenta extra; não é uma
nova medição de economia de tokens.
