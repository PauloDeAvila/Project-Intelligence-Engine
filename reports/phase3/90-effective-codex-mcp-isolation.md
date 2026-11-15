# PIE Fase 3 — Isolamento efetivo do Codex

Data: 2026-11-15

## Resultado

`PASS_NO_MODEL_GATE`. O comando nativo `codex --profile ... mcp list --json` foi executado nos dois homes temporários, sem iniciar modelo.

| Perfil | Servidor habilitado | Servidores desabilitados | Allowlist |
|---|---|---|---|
| Baseline | `blender` | `node_repl`, `pie-blender-optimized`, `pie-def7be8e70`, `pie-web-optimized` | `get_scene_info` |
| Optimized | `pie-blender-optimized` | `blender`, `node_repl`, `pie-def7be8e70`, `pie-web-optimized` | `pie_blender_query_scene` |

Os probes MCP sem modelo passaram nos dois perfis: `initialize`, `tools/list`, `tools/call` e oráculo da fixture. O baseline retornou 1.522 caracteres e 10 ferramentas; o optimized retornou 265 caracteres e 1 ferramenta.

O preflight `89-isolated-codex-preflight.json` confirmou também `mcp_runtime.enabled_servers` exatamente igual ao servidor esperado em cada braço.

## Correção implementada

- `enabled_tools` passou a ser escrito em `mcp_servers.<id>.enabled_tools`, não na raiz do TOML.
- Perfis suportam desabilitação explícita de servidores herdados.
- O preflight verifica servidores habilitados efetivos, allowlist do servidor esperado e o registro nativo do Codex.
- O verificador sem modelo considera apenas servidores habilitados.

Nenhuma sessão de modelo foi executada nesta validação. Economia de tokens permanece não certificada.
