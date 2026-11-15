# Fase 3.14 — validação após isolamento do executor

Commit validado: `cd3d7fb`.

`tools/run_live_codex_pairs.ps1` aceita workspaces limpos separados por condição e repetição, exige o mesmo commit Git entre eles e bloqueia workspaces sujos antes de iniciar o Codex.

Evidências:

- Parse PowerShell: `PASS`.
- `git diff --check`: `PASS`.
- Suíte completa: `538 passed, 5 skipped, 133 subtests passed`.
- Sem o caso HTTP intermitente conhecido: `537 passed, 5 skipped, 1 deselected, 133 subtests passed`.
- Chamadas pagas adicionais: `0`.

Certificação: `NOT_CERTIFIED`; existem somente dois pares comparáveis por domínio, quando são exigidos três.
