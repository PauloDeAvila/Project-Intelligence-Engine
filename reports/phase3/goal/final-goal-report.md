# PIE — relatório final do objetivo

## Estado

`BLOCKED` — infraestrutura local operacional, certificação real ainda não liberada.

## Arquitetura

O fluxo validado localmente é:

`Codex → PIE Gateway → MCP → Blender/Web`

Os gateways `pie-blender-optimized` e `pie-web-optimized` estão registrados. Chamadas locais reais Blender e Web passaram e persistiram telemetria.

## Autenticação

O ambiente original respondeu `AUTH_REMOTE_VALIDATED` em uma única chamada mínima, após pré-voo, usando `--ignore-user-config` e sem MCP. O uso reportado foi 19.935 tokens de entrada, 0 em cache e 10 de saída. Os perfis baseline e optimized isolados continuam `AUTH_MISSING`. Nenhum `auth.json`, token ou cookie foi copiado.

O runner possui pré-voo fail-closed e interrompe antes de `codex exec` quando a autenticação não está disponível.

## Roteamento

Há 5 servidores MCP configurados, 2 rotas PIE e proporção configurada de 0,4. Isso não prova preferência efetiva durante tarefas normais. `node_repl` e os servidores originais permanecem fora da instrumentação PIE.

## Telemetria

SQLite local com WAL, timeout de concorrência, filtros e retenção. Os probes locais registraram Blender e Web; tokens do provedor permanecem `null`.

## Certificação

Nenhum par A/B válido. O probe não executou Blender/Web e não prova autenticação dos perfis isolados. Não é possível calcular economia de tokens, custo, latência comparável ou regressão de qualidade. Redução de caracteres Web não é tratada como redução de tokens.

## Evidências

- Commit atual: `48b6a25`
- Suíte: `531 passed, 5 skipped, 133 subtests`
- Índice local: `CURRENT`, 250 arquivos, 1.782 símbolos
- Relatórios detalhados nesta pasta `goal/`

## Próximo gate

Resolver autenticação segura dos perfis isolados usando mecanismo oficialmente suportado, sem copiar credenciais. Depois, solicitar nova autorização específica para eventual chamada diagnóstica e só então a bateria A/B.
