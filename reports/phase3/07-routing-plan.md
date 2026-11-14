# Fase 3 — plano de roteamento real

## Configuração auditada

- Checkout: `C:\Users\phsra\OneDrive\Documents\ChatGPT\Korum\Project-Intelligence-Engine`
- Configuração Codex: `C:\Users\phsra\.codex\config.toml`
- SHA-256 observado: `0d73bac8e310ab1eabafec40740391557d14f4548d66432410b733ad30320360`
- Servidores MCP ativos relevantes: `blender`, `node_repl`, `pie-def7be8e70`.
- `pie-def7be8e70` aponta para outra raiz e não foi usado.

## Diff planejado, sem aplicação persistente

```diff
 [mcp_servers.blender]
 command = 'C:\\Users\\phsra\\.local\\bin\\uvx.exe'
 args = ["mcp-for-blender"]
+
+[mcp_servers.pie-blender-optimized]
+command = 'C:\\Users\\phsra\\OneDrive\\Documents\\ChatGPT\\Korum\\Project-Intelligence-Engine\\.venv\\Scripts\\python.exe'
+args = ["-m", "pie.gateway.domain", "serve", "--domain", "blender", "--workspace", "C:\\Users\\phsra\\OneDrive\\Documents\\ChatGPT\\Korum\\Project-Intelligence-Engine", "--max-chars", "2400", "--", "C:\\Users\\phsra\\.local\\bin\\uvx.exe", "mcp-for-blender"]
```

O upstream original não é removido nem substituído. O registro foi testado somente numa cópia temporária de `CODEX_HOME`; `codex mcp add` retornou sucesso e `codex mcp get` confirmou o comando PIE.

## Web

O Codex atual usa `node_repl`/serviço interno de browser, não `@playwright/mcp`. `npx`, `npm` e o pacote local Playwright MCP não estão disponíveis. Não foi criada uma entrada Web inválida. O plano pendente é:

```text
pie-web-optimized -> python -m pie.gateway.domain serve --domain web -- ... @playwright/mcp
```

Isso requer instalar/disponibilizar o upstream Playwright MCP e autorização para registrar uma nova entrada no `CODEX_HOME`.

## Estado após autorização

- Backup: `C:\\Users\\phsra\\.codex\\config.toml.pie-phase3-backup-20261114`
- SHA-256 original/backup: `0d73bac8e310ab1eabafec40740391557d14f4548d66432410b733ad30320360`
- SHA-256 atual: `09f36f960ed1a7100e984e18a0e51e9e7485c22c774467526c1ccbb4347fcb08`
- `pie-blender-optimized`: registrado e confirmado por `codex mcp get`.
- `blender` original: preservado.
- Auditoria: 1 rota PIE de 4 servidores ativos; `configured_routing_ratio=0.25`.
- Web: `BLOCKED`, pois `npm`/`npx` e `@playwright/mcp` não estão disponíveis.

Rollback:

```powershell
Copy-Item -LiteralPath "$env:USERPROFILE\\.codex\\config.toml.pie-phase3-backup-20261114" -Destination "$env:USERPROFILE\\.codex\\config.toml" -Force
```
