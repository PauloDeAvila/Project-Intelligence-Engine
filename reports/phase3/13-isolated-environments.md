# Fase 3.4 — ambientes baseline e optimized

| Verificação | Baseline | Optimized |
|---|---|---|
| `config.toml` válido | PASS | PASS |
| Modelo `gpt-5.6-luna` | PASS | PASS |
| Worktree limpo | PASS | PASS |
| Autenticação disponível | `AUTH_MISSING` | `AUTH_MISSING` |
| MCP Blender esperado | `blender` PASS | `pie-blender-optimized` PASS |
| MCP Web esperado | `playwright-baseline` PASS | `pie-web-optimized` PASS |
| Pré-voo | BLOCKED | BLOCKED |

Os perfis foram criados em diretórios temporários fora do repositório. Nenhum `auth.json`, token ou cookie foi copiado. O baseline inicialmente não tinha o servidor Web direto; o erro foi corrigido no diretório temporário e o pré-voo passou a detectar apenas `PRECHECK_AUTH_MISSING`.

O ambiente original não foi alterado durante essa investigação.
