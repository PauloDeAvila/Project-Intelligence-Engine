# PIE — relatório final do objetivo

## Estado

`BLOCKED` — infraestrutura local operacional, certificação real ainda não liberada.

## Arquitetura

O fluxo validado localmente é:

`Codex → PIE Gateway → MCP → Blender/Web`

Os gateways `pie-blender-optimized` e `pie-web-optimized` estão registrados. Chamadas locais reais Blender e Web passaram e persistiram telemetria.

## Autenticação

O ambiente original responde `AUTH_VALIDATED_LOCAL` via `codex login status`. Os perfis baseline e optimized isolados respondem `AUTH_MISSING`. Nenhum `auth.json`, token ou cookie foi copiado.

O runner possui pré-voo fail-closed e interrompe antes de `codex exec` quando a autenticação não está disponível.

## Roteamento

Há 5 servidores MCP configurados, 2 rotas PIE e proporção configurada de 0,4. Isso não prova preferência efetiva durante tarefas normais. `node_repl` e os servidores originais permanecem fora da instrumentação PIE.

## Telemetria

SQLite local com WAL, timeout de concorrência, filtros e retenção. Os probes locais registraram Blender e Web; tokens do provedor permanecem `null`.

## Certificação

Nenhum par A/B válido. Não é possível calcular economia de tokens, custo, latência comparável ou regressão de qualidade. Redução de caracteres Web não é tratada como redução de tokens.

## Evidências

- Commit atual: `48b6a25`
- Suíte: `531 passed, 5 skipped, 133 subtests`
- Índice local: `CURRENT`, 250 arquivos, 1.782 símbolos
- Relatórios detalhados nesta pasta `goal/`

## Próximo gate

Resolver autenticação segura dos perfis isolados usando mecanismo oficialmente suportado, sem copiar credenciais. Depois, solicitar nova autorização específica para eventual chamada diagnóstica e só então a bateria A/B.
