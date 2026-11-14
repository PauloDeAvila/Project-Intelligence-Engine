# Fase 1 — estratégia segura de autenticação

Estratégias avaliadas:

- Login independente por perfil: compatível em princípio, mas exige intervenção/login adicional.
- Cópia de `auth.json`: rejeitada por exposição e falta de necessidade.
- Link ou compartilhamento não documentado do arquivo de autenticação: não selecionado sem validação de compatibilidade e segurança.
- Perfis temporários usando o `CODEX_HOME` autenticado original: tecnicamente promissor, mas ainda requer validação de isolamento MCP e autorização para criar arquivos de perfil temporários no diretório do Codex.

Estado: `READY_FOR_AUTH_PROBE`, não `READY_FOR_BENCHMARK`.

O próximo teste permitido deve ser uma única chamada diagnóstica autorizada, usando o `CODEX_HOME` original e configuração MCP temporária/reversível, sem copiar credenciais. A bateria de 12 chamadas continua bloqueada.
