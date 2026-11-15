# Fase 1 — estratégia segura de autenticação

Estratégias avaliadas:

- Login independente por perfil: compatível em princípio, mas exige intervenção/login adicional.
- Cópia de `auth.json`: rejeitada por exposição e falta de necessidade.
- Link ou compartilhamento não documentado do arquivo de autenticação: não selecionado sem validação de compatibilidade e segurança.
- Perfis temporários usando o `CODEX_HOME` autenticado original: tecnicamente promissor, mas ainda requer validação de isolamento MCP e autorização para criar arquivos de perfil temporários no diretório do Codex.

Estado: `AUTH_REMOTE_VALIDATED_ORIGINAL_ONLY`, não `READY_FOR_BENCHMARK`.

A chamada diagnóstica autorizada foi executada com o `CODEX_HOME` original, `--ignore-user-config` e sem MCP. A bateria de 12 chamadas continua bloqueada porque os perfis isolados ainda não possuem autenticação.
