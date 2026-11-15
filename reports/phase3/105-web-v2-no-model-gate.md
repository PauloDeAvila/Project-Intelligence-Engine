# PIE Fase 3 — gate Web v2 sem modelo

`PASS_NO_MODEL_GATE`. A fixture local foi navegada com Playwright MCP fixado em `@playwright/mcp@0.0.85`.

| Braço | Servidor | Ferramentas | Resultado |
|---|---|---|---|
| Baseline | `playwright-baseline` | `browser_navigate`, `browser_snapshot` | PASS |
| Optimized | `pie-web-optimized` | navegação, snapshot, recuperação | PASS |

O probe real confirmou navegação, snapshot, recuperação PIE e preservação de referências nativas. A resposta reduziu de 17.585 para 1.256 caracteres (92,858%), mas isso não é economia certificada de tokens. Nenhuma sessão de modelo ou quota foi consumida.
