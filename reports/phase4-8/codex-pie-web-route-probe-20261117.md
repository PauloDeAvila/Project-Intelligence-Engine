# Sonda Codex → PIE Web

O Codex `gpt-5.6-luna` usou exclusivamente `pie-web-optimized` para abrir a
fixture local `http://127.0.0.1:8766/index.html`, obter dois snapshots e clicar
no botão de revelação do marcador. Nenhum servidor proibido foi chamado.

- Título confirmado: `PIE Phase 3 Fixture`.
- Marcador confirmado: `PIE_WEB_FIXTURE_V1`.
- Chamadas MCP: `browser_navigate`, dois `browser_snapshot` e `browser_click`.
- Tokens reportados: 226.276 de entrada, 205.440 cacheados, 20.836 não
  cacheados, 797 de saída e 413 de raciocínio.
- Configuração persistente e páginas externas: não modificadas.

O resultado comprova o caminho Codex → `pie-web-optimized` → fixture Web local,
mas não é certificação A/B de economia: foi uma única sonda de integração, sem
braço baseline e sem comparação pareada.

A página registrou um erro de console; sua origem não foi investigada nesta
sonda e isso permanece uma limitação da evidência.
