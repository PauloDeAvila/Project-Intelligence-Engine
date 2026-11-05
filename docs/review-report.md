# Independent code review — evidence report

## Identificação

- Repository / branch / base SHA / head SHA: `Project-Intelligence-Engine` / `feat/evidence-atoms-v3` / `01ddc506529d455c3e4fb7f4d3aec7622bf930d7` / `5b5e2200b856e4bc63fdab128536c1b6a5f282fb`
- Autor da implementação / revisor: Codex / separate read-only review pass
- Objetivo: compactar evidências verificadas, reutilizá-las entre consultas e distribuir contexto por agente sem entregar fatos não comprovados.
- Decisão: **APPROVE FOR PR**; merge em `main` depende do CI remoto exigido pelo ruleset.
- Limites: revisão estática local, suíte completa local e verificação da configuração remota; não houve execução NVIDIA após a última correção de cache.

## Sumário executivo

A branch adiciona Evidence Atoms hash-backed, cache persistente invalidado por geração/SHA-256, seleção adaptativa por cláusula, entrega estruturada e Context Mesh para agentes. A revisão encontrou dois riscos de alta severidade: cache dependente dos requisitos da primeira consulta e entrega `READY` para índice parcial. Ambos foram corrigidos em `ad48fbb` e receberam testes de regressão.

O cache agora persiste a linha-fonte completa e deriva o recorte semântico por consulta; entradas antigas sem `source_text` são reconstruídas. A entrega exige estado `CURRENT` tanto do índice quanto do contexto. O Context Mesh só encaminha fatos quando `can_deliver_atoms` é verdadeiro.

## Arquivos e símbolos alterados

| Arquivo | Símbolo/contrato | Evidência |
| --- | --- | --- |
| `src/pie/retrieval/evidence_atoms.py` | `EvidenceAtomCache`, `_source_atoms`, `_select_atoms`, `build_proof_context` | `tests/test_evidence_atoms.py`; cache SQLite e payload `pie-proof-context-v1` |
| `src/pie/retrieval/context_mesh.py` | `ContextMesh.build`, `search`, `visualization` | `tests/test_context_mesh.py`; payload `pie-context-mesh-v1` |
| `src/pie/interfaces/mcp_server.py` | `pie_build_proof_context`, `pie_build_context_mesh` | MCP dispatch/stdio tests |
| `tests/test_evidence_atoms.py` | cache, invalidação, cobertura, deduplicação | seis testes direcionados |
| `tests/test_context_mesh.py` | roteamento, grafo, estado parcial, MCP | seis testes direcionados |
| `PROJECT.md`, `docs/*` | escopo, arquitetura, ADRs e mapa de contexto | documentação alinhada ao código atual |

## Matriz de impacto e rastreabilidade

| Símbolo | Consumidores | Invariante | Risco residual |
| --- | --- | --- | --- |
| `EvidenceAtomCache` | `build_proof_context` em CLI/MCP e subprocessos MCP | cache só é válido com geração atual e manifest SHA-256 válido | arquivos muito grandes aumentam o custo de validação dos hashes |
| `_source_atoms` | seleção adaptativa e cache de faixas | texto persistido é independente dos requisitos da consulta | cache antigo é descartado/reconstruído por ausência de `source_text` |
| `_delivery_status` | `build_proof_context`, `ContextMesh` | índice/contexto não `CURRENT` nunca vira `READY` | estados dinâmicos fora do índice continuam fora do escopo |
| `ContextMesh.build` | `pie_build_context_mesh` e futuro Cavecast | fatos não verificados não entram em assignments | ações de arquivo/browser ainda não são executadas por esta camada |
| MCP dispatch | clientes JSON-RPC/stdio | argumentos desconhecidos e shapes inválidos são rejeitados | compatibilidade com hosts MCP externos ainda não foi testada remotamente |

Chamadas dinâmicas e comportamento de runtime não são certificados pelo grafo estático; o sistema declara essa limitação nos contratos.

## Achados

### Riscos encontrados e resolvidos

- **R1 / alta / resolvido** — cache de átomos dependia do recorte criado pela primeira lista de requisitos. Correção: persistir `source_text`, derivar `_compact_text` e semanticização na leitura, e usar `evidence-cache-v2` na chave. Teste: `test_different_questions_share_the_same_atom_catalog`.
- **R2 / alta / resolvido** — índice/contexto parcial podia ser entregue como `READY`. Correção: `_delivery_status` exige `index_state == CURRENT` e `context_state == CURRENT`; Context Mesh bloqueia assignments não prontos. Teste: `test_partial_index_is_blocked_from_agent_delivery`.

## Matriz de execução

| Camada | Comando / ambiente | Resultado |
| --- | --- | --- |
| Unitário | `py -3 -m unittest discover -s tests -p test_pie_unit.py -v` | 14 passaram |
| Integração | `py -3 -m unittest discover -s tests -p test_pie_integration.py -v` | 10 passaram |
| E2E | `py -3 -m unittest discover -s tests -p test_pie_e2e.py -v` | 1 passou |
| Direcionado | `py -3 -m pytest tests/test_evidence_atoms.py tests/test_context_mesh.py -q` | 12 passaram |
| Regressão global pytest | `rtk test py -3 -m pytest -q` | 334 passaram, 2 ignorados, 126 subtestes |
| Regressão global unittest | `py -3 -m unittest discover -s tests -v` | 336 passaram, 2 ignorados |
| Verificação de projeto | `py -3 tools/verify_project.py` | unit, component, integration, e2e, regression e build passaram |
| Build/import | `py -3 tools/check_install.py` | passou; pacote 0.1.0 construído/instalado |
| Compile | `py -3 -m compileall -q src tools tests` | passou |
| Diff | `git diff --check` | passou |

## Proteção da branch

- Ruleset remoto `Protect main`: ativo.
- PR obrigatória: confirmada via `gh api repos/.../rulesets/26297201`.
- Check exigido: `Project Verification`.
- Exclusão e non-fast-forward: bloqueados.
- CI remoto: a primeira execução encontrou apenas a necessidade de declarar `PYTHONPATH` no subprocesso MCP do teste; a correção está em `5b5e220` e deve ser validada pelo GitHub Actions antes do merge.

## Veredito

- Critérios funcionais locais: cumpridos.
- Critérios de regressão/build: cumpridos localmente.
- Critério remoto: pendente de push, PR e `Project Verification`.
- Recomendação: publicar a branch, abrir PR contra `main`, aguardar os checks e só então fazer o merge protegido.
