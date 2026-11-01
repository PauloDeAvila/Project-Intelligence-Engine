# PIE V0.1 audit — 2026-10-31

## Status: V0.1 STABILIZED — PRODUCTION GATE IMPROVED
This is an evidence-based record, not an unconditional certification.

## Verified from GitHub
- GitHub Actions recognized and ran the Validation Gate workflow: run 41254815589.
- "Starter Unit Tests" job succeeded in that run; this establishes a successful execution for the then-existing tests.
- The local verification matrix now executes unit, integration, E2E, regression and build checks; the component tier is explicitly not applicable for V0.1.
- A subsequent commit 0fca3892c99022991a4cfe178f79c93a961ab352 added tests for command success, failure, missing executable, result evidence, and fail-closed configuration. Refer to Actions for the outcome of this newer run; do not assume it passed.
- GitHub UI now shows active ruleset `Protect main`, targeting the default `main` branch and requiring pull requests plus `Project Verification`.
- Ruleset details read from GitHub API: active on default branch, requires a PR and `Project Verification`, but requires 0 human approvals.
- Pull Request #1 run 41266348745 passed `Project Verification`, `Windows Compatibility` and `Starter Unit Tests`.

## Implemented controls
- Agent engineering contract (AGENTS.md), scope guard, dependency impact analysis and full regression rules.
- Read-only reviewer protocol (PONTO.md) with detailed report template.
- Project bootstrap and independent-review agent skills.
- Python verification runner, six named test tiers, JSON result evidence, and GitHub Actions job.
- Branch protection setup and verification guide (docs/branch-protection.md).
- V0.1 Python package, SQLite index, CLI workflow and tests.

## Known gaps
1. V0.1 intentionally supports Python only; additional languages require new adapters and tests.
2. The verification runner cannot prove full functional coverage just by running commands. A project's test design, coverage and independent review remain essential.
3. Branch rulesets must be configured in GitHub and enforcement validated via a failing PR and a passing PR.
4. A deliberately failing-PR enforcement test remains a follow-up; the active ruleset configuration is verified in the GitHub UI and the stabilization PR checks passed.
5. A separate autonomous review agent is not running as a service. The skill defines the process for an independent read-only reviewer when supported.

## Required acceptance evidence for a new project
- Actual checks specified in ci/checks.json; execution results attached.
- Successful unit, component, integration, E2E and full regression checks as applicable, with exclusions justified.
- A reviewed change-impact report identifying relevant direct and indirect references.
- GitHub ruleset active for main, requiring PR and passing Project Verification status.
- Evidence that a failing PR cannot be merged.

## Local verification evidence
- Bundled Python 3.12 runtime: complete regression suite passed, 23 tests.
- `tools/verify_project.py`: unit passed, component not-applicable, integration passed, E2E passed, regression passed, package-install build passed.
- `python tools/check_install.py`: package installed into an isolated target and imported successfully.
- `python tools/benchmark_index.py`: baseline recorded for 100 files and 200 symbols in 0.0441 seconds on the local runtime.
- `python -m compileall -q src tools tests`: passed.
- `.gitignore` patterns, snapshot parsing, literal `LIKE` escaping, Unicode paths, unreadable-file handling, concurrent-read behavior and SQLite integrity are covered by the expanded 23-test suite.

## Conclusion
The V0.1 functional slice is locally and remotely verified under the recorded commands. The active branch ruleset and CI matrix now address the principal governance gaps; a deliberately failing PR should still be used as the final enforcement proof.

## Segunda auditoria — correções preparadas em 2026-11-01

- A varredura produz caminhos incrementalmente; o indexador retém apenas o conjunto de caminhos vistos para reconciliação. `read_snapshot` lê no máximo `max_bytes + 1` bytes e hash/parser ainda usam o mesmo snapshot.
- Falhas de leitura em arquivos ou diretórios preservam as linhas existentes naquela execução. Uma exclusão confirmada só remove as linhas na varredura subsequente, quando o caminho pode ser observado como ausente.
- As regras `.gitignore` agora contemplam arquivos aninhados, diretórios, negações ordenadas e curingas por componente/`**`. A implementação permanece um subconjunto explícito; escapes Git para `#`, `!` e espaço final não são suportados.
- `check_install.py` cria um ambiente virtual limpo, instala o pacote e verifica o executável `pie` em `--version`, `init`, `index`, `status`, `search` e `symbol` com resultados JSON.
- O benchmark aceita tamanhos e número de consultas configuráveis e mede tempo de indexação, buscas repetidas e pico de memória Python rastreado.
- Evidência local: 28 testes aprovados; matriz completa e instalação CLI aprovadas. Benchmark Windows, Python empacotado 3.12: 5.000 arquivos, 10.000 símbolos, 10,5526s; 7.805.045 bytes de pico via `tracemalloc`; 100 consultas em 3,4515s.
- Limite: a medição de `tracemalloc` não inclui alocações nativas do SQLite ou do sistema operacional; a lista de caminhos e o conjunto de caminhos vistos continuam crescendo conforme o projeto.
- A validação remota desta atualização e o teste deliberadamente falho de enforcement da ruleset ainda precisam ser registrados após publicar o commit atualizado da PR #1.
