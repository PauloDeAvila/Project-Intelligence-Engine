# Independent code review — evidence report

## Identificação
- Repository / branch / base SHA / head SHA: `Project-Intelligence-Engine` / `stabilize-v0-1` / `ccf53c9` / working tree stabilization changes
- Autor da implementação / revisor: Codex / separate read-only review pass
- Objetivo e critérios de aceite: deliver PIE V0.1 local Python indexing, SQLite persistence and CLI workflow defined in `PROJECT.md`
- **Decisão**: REQUEST CHANGES — V0.1 STABILIZATION IMPLEMENTED, FINAL PR ENFORCEMENT TEST PENDING
- **Limites da inspeção**: static local review, complete diff, local tests and compile check; remote CI passed on the stabilization PR, while deliberate failing-PR enforcement remains pending.

## Sumário executivo

The change hardens the V0.1 slice with `.gitignore` rules, same-snapshot hashing/parsing, SQLite integrity checks, literal search escaping, isolated installation validation and a 100-file benchmark. Local verification passed. GitHub now has an active `Protect main` ruleset requiring PRs and `Project Verification`; a deliberately failing PR enforcement test remains pending.

## Arquivos e símbolos alterados

| Arquivo:linha | Símbolo / contrato | Mudança | Justificativa | Evidência |
| --- | --- | --- | --- | --- |
| `src/pie/scanning/discovery.py:10` | `discover_files` | Stable Python inventory with `.gitignore` exclusions and symlink rejection | Scanner acceptance criteria | `tests/test_pie_unit.py` |
| `src/pie/scanning/hashing.py:5` | `sha256_file` | Chunked content hashing | Incremental change detection | `tests/test_pie_unit.py` |
| `src/pie/indexing/python_ast.py:7` | `parse_python` / `parse_python_content` | Classes, functions, methods, nested scopes and imports from one snapshot | V0.1 symbol extraction | `tests/test_pie_unit.py` |
| `src/pie/indexing/indexer.py:8` | `index_project` | Atomic reconciliation into SQLite | Persistence and deletion behavior | `tests/test_pie_integration.py` |
| `src/pie/interfaces/cli.py:22,41,51,61` | init/status/search/symbol/main | JSON CLI workflow with literal wildcard escaping | User-facing V0.1 contract | `tests/test_pie_e2e.py` |
| `src/pie/storage/database.py:6` | SQLite schema / `connect` | Files, symbols and imports with foreign keys | Durable evidence model | Integration tests |

## Matriz de impacto e rastreabilidade

| Símbolo alterado | Referências diretas | Consumidores transitivos | Invariantes/contratos | Testes protetores | Risco e confiança |
| --- | --- | --- | --- | --- | --- |
| `discover_files` | `index_project` | CLI `index` | Only eligible files below root; stable relative paths | Unit discovery test | Medium / high |
| `parse_python` | `index_project` | SQLite symbol/import rows; CLI queries | Parse errors are observable and do not abort indexing | Unit invalid syntax test | Medium / high |
| `index_project` | CLI `index` | Persistent `.pie/index.sqlite3` | Changed/deleted files reconcile; source is not edited | Integration update/delete tests | High / high |
| CLI query functions | `main` | Shell users and future agent adapters | JSON output and evidence paths | E2E workflow | Medium / high |

Dynamic/reflection-based consumers were not found in the repository; text search cannot prove none exist outside inspected files.

## Achados

No blocking functional finding reproduced in the reviewed scope.

Known limitations are intentional and documented: Python-only AST parsing, no semantic reference resolution, no FTS ranking and no MCP. A deliberately failing PR enforcement test is still outstanding.

## Matriz de execução

| Camada | Comando, ambiente e versão | Passou | Falhou | Pulou | Logs / artefatos / bloqueios |
| --- | --- | ---: | ---: | ---: | --- |
| Unitário | Bundled Python 3.12; `python -m unittest discover -s tests -p test_pie_unit.py -v` | 10 | 0 | 0 | Passed |
| Componente | `ci/checks.json` | — | — | 1 tier | Explicitly not applicable for V0.1 |
| Integração/contratos | `python -m unittest discover -s tests -p test_pie_integration.py -v` | 3 | 0 | 0 | Passed |
| E2E | `python -m unittest discover -s tests -p test_pie_e2e.py -v` | 1 | 0 | 0 | Passed |
| Regressão global | `python -m unittest discover -s tests -v` | 23 | 0 | 0 | Passed |
| Build/lint/tipos/segurança aplicável | `python tools/check_install.py`; `python -m compileall -q src tools tests` | 2 commands | 0 | 0 | Passed; no lint/type checker configured |
| Project verification | `python tools/verify_project.py` | unit, integration, E2E, regression, package-install build | 0 | component | `verification-results.json` generated and ignored |
| Remote PR CI | GitHub Actions run `41266348745` | Project Verification, Windows Compatibility, Starter Unit Tests | 0 | 0 | All three jobs passed |

## Impacto por subsistema

- Scanner: local, read-only, medium risk; symlinked files are excluded.
- Parser: local, medium risk; unresolved dynamic semantics remain out of scope.
- Storage: shared durable state, high risk; foreign-key cascade and transactional indexing are covered by integration tests.
- CLI: public local contract, medium risk; end-to-end JSON workflow is covered.
- CI/governance: real commands are configured; active ruleset `Protect main` requires PR and `Project Verification`.

## Proteção da branch

- PR obrigatória: confirmada no GitHub UI via active `Protect main` ruleset targeting default `main`.
- Checks exigidos: `Project Verification` from GitHub Actions.
- Aprovações: ruleset ativa define `required_approving_review_count: 0`; exige PR, mas não exige aprovação humana.
- Regras confirmadas na API: `Protect main` ativa em `~DEFAULT_BRANCH`, exige pull request e status `Project Verification`, bloqueia exclusão e non-fast-forward; bypass actors vazio.
- Bloqueios pendentes: run a deliberately failing PR and confirm merge is blocked; then verify a passing PR path.

## Veredito

- Critérios cumpridos: V0.1 functional acceptance and local automated checks.
- Critérios não cumpridos: deliberately failing PR enforcement evidence.
- Evidências: test matrix above, `ci/checks.json`, `PROJECT.md`, `docs/architecture.md`.
- Risco residual: semantic resolution, non-Python languages, large repositories and remote enforcement are unvalidated.
- Próximo passo: perform the deliberately failing-PR enforcement test; PR #1 and its Ubuntu/Windows checks are already published and passing.
