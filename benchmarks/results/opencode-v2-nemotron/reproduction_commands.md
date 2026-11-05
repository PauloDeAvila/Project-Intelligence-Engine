# Comandos para reproduzir o experimento

Este documento lista os comandos necessários para reproduzir a verificação existente do repositório PIE. O benchmark real com modelo Nemotron (WITH_PIE vs WITHOUT_PIE) **não pôde ser executado** porque OpenCode 2.2.5 não está instalado e nenhum modelo Nemotron está disponível.

## Pré-requisitos

- Python 3.12+ (testado com 3.13.17)
- Git
- Acesso à rede para `git clone` e `git pull`
- `npx` disponível para Pyright (opcional, apenas para verificação estática)

## Passos

### 1. Clonar o repositório em pasta isolada

```powershell
git clone https://github.com/PauloDeAvila/Project-Intelligence-Engine.git pie
cd pie
```

### 2. Atualizar para o commit de referência da branch experimental

```powershell
git checkout exp/opencode-remote-orchestrator
git pull --ff-only origin exp/opencode-remote-orchestrator
git rev-parse HEAD
```

SHA esperado: `0d5348b5cd4ba957ad11f714e859d9e1439d9b0e`

### 3. Executar a suíte completa de testes

```powershell
python -m unittest discover -s tests -v
```

Resultado esperado: 131 testes, todos passando (exit code 0).

### 4. Executar check_install

```powershell
python tools/check_install.py
```

Resultado esperado: exit code 0, versão PIE 0.1.0, todos os comandos CLI verificados.

### 5. Executar Pyright

```powershell
npx pyright src
```

Resultado esperado neste ambiente: 21 erros de tipo, exit code 1.

### 6. Verificar o contrato OpenCode v2 (requer OpenCode instalado)

Este passo **não pôde ser executado** pois OpenCode não está instalado:

```powershell
# Gerar config isolada (exemplo, requer OpenCode para validar)
python tools/create_opencode_pie_config.py --root . --python python.exe --output opencode-pie.json

# Iniciar OpenCode isolado (requer binário opencode)
# opencode serve --hostname 127.0.0.1 --port 4097

# Validar contrato (requer OPENCODE_PASSWORD)
# python tools/verify_opencode_runtime.py --url http://127.0.0.1:4097 --root . --config opencode-pie.json
```

## Benchmark WITH_PIE / WITHOUT_PIE

Não executado. Requereria:
1. OpenCode 2.2.5 instalado e acessível via PATH
2. Modelo Nemotron disponível localmente ou via endpoint autorizado
3. `OPENCODE_PASSWORD` definido para autenticação Basic na API v2
4. Servidor OpenCode rodando em `http://127.0.0.1:4097` com config MCP do PIE
5. Conjunto de perguntas de benchmark definido (não existe no repositório)

## Sanitização

Todos os arquivos em `benchmarks/results/opencode-v2-nemotron/` são sanitizados:
- Nenhum token, senha ou segredo incluído
- Nenhuma configuração pessoal incluída
- Nenhum dado privado incluído
- Nenhum arquivo de outros projetos incluído

## Publicação

Branch: `bench/opencode-v2-nemotron-results`  
Commit: `test(benchmark): record OpenCode v2 Nemotron PIE comparison`
