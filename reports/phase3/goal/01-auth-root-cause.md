# Fase 1 — causa raiz da autenticação

O Codex original está autenticado por conta ChatGPT. `codex login status` retornou `Logged in using ChatGPT` no `C:\Users\phsra\.codex` original.

Os perfis temporários receberam apenas `config.toml`. O runner confirmou `AUTH_MISSING` antes de iniciar o modelo. A causa comprovada é a ausência de um mecanismo de autenticação utilizável no `CODEX_HOME` isolado; a hipótese de sessão inválida não foi testada remotamente porque isso exigiria modelo.

Nenhum segredo foi lido, copiado ou exportado. O status foi registrado apenas como estado sanitizado.
