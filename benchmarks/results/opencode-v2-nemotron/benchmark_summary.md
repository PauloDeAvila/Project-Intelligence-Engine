# PIE vs Nemotron Benchmark — OpenCode v2

**Repository:** https://github.com/PauloDeAvila/Project-Intelligence-Engine  
**Branch:** `exp/opencode-remote-orchestrator`  
**Commit:** `0d5348b5cd4ba957ad11f714e859d9e1439d9b0e`  
**Date:** 2026-11-05 (UTC)

## Resultado

O benchmark comparativo **WITH_PIE vs WITHOUT_PIE com modelo Nemotron não pôde ser executado**.

Este é um **bloqueio real, documentado**, e não um resultado negativo disfarçado de sucesso. Nenhum resultado foi fabricado.

## Motivo do bloqueio

| Condição | Status | Motivo |
|----------|--------|--------|
| OpenCode 2.2.5 instalado | ❌ Não instalado | Nenhum binário `opencode` encontrado no PATH |
| npm/npx disponível | ❌ Não disponível | Sem gerenciador de pacotes Node para instalar OpenCode |
| Modelo Nemotron disponível | ❌ Não disponível | Sem endpoint de modelo local nem configurado |
| `OPENCODE_PASSWORD` | ❌ Não definido | Sem senha de autenticação Basic para API v2 local |
| Bearer do gateway público | ❌ Proibido | Token divulgado, não rotacionado, não deve ser usado |
| Instalação de ferramentas | ❌ Proibida | Restrição de segurança: não instalar ferramentas desconhecidas |

Por conseguinte:
- **WITH_PIE:** Não executado (OpenCode ausente, sem modelo, sem MCP conectado)
- **WITHOUT_PIE:** Não executado (OpenCode ausente, sem modelo)

## O que foi executado (suíte existente do repositório)

Como o benchmark real com modelo não pôde rodar, foram executados os artefatos de verificação existentes no repositório:

### Testes unitários/integração/E2E

```
python -m unittest discover -s tests -v
```

- **Total:** 131 testes
- **Passou:** 131
- **Falhou:** 0
- **Erros:** 0
- **Exit code:** 0
- **Duração:** 6.945s

Todos os testes de domínio PIE passaram, incluindo:
- `test_pie_unit` — scanner, parser, gitignore, hashing
- `test_pie_integration` — persistência do índice, migrações, incremental
- `test_pie_e2e` — fluxo CLI init/index/status/search/symbol
- `test_opencode_v2` — contrato da API OpenCode v2 (mocks, sem rede)
- `test_opencode_completion` — contrato de conclusão assíncrona (mocks)
- `test_opencode_pie_config` — geração de config isolada do OpenCode
- `test_opencode_runtime_contract` — pré-voo de contrato runtime v2
- `test_orchestrator` — orquestrador, gateway, webhook GitLab

### check_install

```
python tools/check_install.py
```

- **Resultado:** PASSOU (exit code 0)
- **Versão PIE:** 0.1.0
- Comandos CLI verificados: `--version`, `init`, `index`, `status`, `search`, `symbol`, `definitions`, `references`, `analysis`

### Pyright (estática)

```
npx pyright src
```

- **Versão Pyright:** 1.1.414
- **Erros:** 21
- **Avisos:** 0
- **Exit code:** 1
- **Resultado:** ERROS DE TIPO (não limpo)

Nota: a documentação do repositório registra um resultado anterior de 120/120 Pyright-clean no commit `c59071bc`; este ramo não está limpo de tipos neste ambiente.

## Ferramentas MCP do PIE disponíveis

O servidor MCP stdio do PIE expõe as seguintes ferramentas (não invocadas, pois não há OpenCode para consumi-las):

1. `pie_project_status`
2. `pie_search_symbols`
3. `pie_inspect_symbol`
4. `pie_build_graph`
5. `pie_relationships`
6. `pie_build_context`
7. `pie_find_definitions`
8. `pie_find_references`
9. `pie_analysis_summary`

## Perguntas avaliadas

**0 perguntas** — nenhum cenário de benchmark com modelo Nemotron foi definido ou executado neste repositório. Os testes existentes usam mocks (sem modelo, sem rede).

## Tokens, latência, taxa de acerto

| Métrica | WITH_PIE | WITHOUT_PIE |
|---------|----------|-------------|
| Perguntas avaliadas | 0 | 0 |
| Acertos | 0 | 0 |
| Erros | 0 | 0 |
| Tokens de entrada | não informado | não informado |
| Tokens de saída | não informado | não informado |
| Latência (s) | não informado | não informado |
| Chamadas MCP | nenhuma | nenhuma |
| IDs de sessão | nenhuma | nenhuma |

## Falhas e limitações encontradas

1. **OpenCode não instalado:** Não há binário `opencode` no sistema. Não é possível iniciar um servidor local na porta 4097 nem criar sessões.
2. **Sem modelo Nemotron:** Não há endpoint de modelo local nem credenciais para acessar um modelo Nemotron.
3. **Sem `OPENCODE_PASSWORD`:** A autenticação Basic da API v2 requer uma senha que não está configurada.
4. **Bearer do gateway proibido:** O token divulgado não deve ser usado, conforme restrição de segurança.
5. **Sem benchmark de perguntas definido:** O repositório contém testes unitários com mocks, não um conjunto de perguntas de benchmark para um modelo LLM.

## Comandos para reproduzir (ambiente de teste isolado)

```powershell
# 1. Clonar o repositório
git clone https://github.com/PauloDeAvila/Project-Intelligence-Engine.git pie
cd pie
git checkout exp/opencode-remote-orchestrator
git pull --ff-only origin exp/opencode-remote-orchestrator

# 2. Executar suíte de testes
python -m unittest discover -s tests -v

# 3. Executar check_install
python tools/check_install.py

# 4. Executar Pyright
npx pyright src

# 5. Verificar commit
git rev-parse HEAD
```

## Publicação

Branch: `bench/opencode-v2-nemotron-results`  
Commit message: `test(benchmark): record OpenCode v2 Nemotron PIE comparison`  
Apenas relatórios e artefatos sanitizados do benchmark são incluídos. Nenhum token, senha, configuração pessoal ou dado privado.
