# PIE — instalação MCP e operação local (pré-release V1)

Este guia cobre a branch `feat/pie-context-intelligence-v2`; **não** declara que o pacote já é uma release 1.0. Python 3.12+ é necessário. A análise atual concentra-se em arquivos Python.

## Instalação no Windows (PowerShell)

Execute em um terminal com Python 3.12+ disponível. Substitua `C:\caminho\projeto` pelo projeto **que deseja indexar**.

```powershell
python -m pip install "git+https://github.com/PauloDeAvila/Project-Intelligence-Engine.git@feat/pie-context-intelligence-v2"
if ($LASTEXITCODE -ne 0) { throw "Falhou a instalação do PIE" }
pie-setup --project "C:\caminho\projeto" --clients vscode codex claude
```

Em uma máquina onde o checkout do PIE já existe:

```powershell
python -m pip install -e .
pie-setup --project "C:\caminho\projeto"
```

**Uma linha**, depois de o PIE já estar instalado:

```powershell
pie-setup --project "C:\caminho\projeto"
```

O comando inicializa `<projeto>/.pie/index.sqlite3`, indexa o código e, **apenas se o índice estiver CURRENT**, registra as integrações selecionadas. Falhas no índice impedem a criação de novas configurações MCP. O instalador não exige credenciais de modelos, 9Router, ChatGPT nem serviço de rede para indexar.

## Registros MCP gerados

Um identificador `pie-<hash-da-raiz>` é estável por pasta de projeto, evitando colisões quando houver vários workspaces.

| Cliente | Arquivo no projeto | Estrutura |
| --- | --- | --- |
| VS Code / agentes locais | `.vscode/mcp.json` | `{"servers": {...}}` |
| Codex CLI ou extensão, escopo do projeto | `.codex/config.toml` | `[mcp_servers.pie-XXXXXXXXXX]` |
| Claude Code (CLI e Code no desktop) | `.mcp.json` | `{"mcpServers": {...}}` |

O executável configurado é o caminho absoluto do Python que executou `pie-setup`; os argumentos são `-m pie.interfaces.mcp_server --root <projeto>`. O servidor utiliza stdio local, não uma porta HTTP. Se houver uma entrada do PIE com o mesmo nome mas comando diferente, o instalador **não sobrescreve silenciosamente**: falha e pede revisão. Entradas de terceiros são preservadas.

A configuração `.mcp.json` também usa o formato portátil compatível com alguns clientes Copilot; a estrutura de `.vscode/mcp.json` é diferente. VS Code pode descobrir os dois formatos: se mostrar duas instâncias do mesmo servidor, use apenas uma fonte de configuração. Em VS Code, abra **MCP: List Servers** e confira o registro; em Codex, use `codex mcp list`; em Claude Code, use `/mcp` ou `claude mcp list`. O cliente pode solicitar aprovação/confiança do servidor. Estar registrado não garante que um agente escolha automaticamente `pie_query`: configure instruções do agente para priorizá-lo.

**Claude Desktop chat** (aplicação de conversas) possui configuração MCP diferente de **Claude Code**. O instalador atua em Claude Code. Não altera configurações globais nem o `claude_desktop_config.json`.

## Múltiplos workspaces e isolamento

Para cada projeto, execute `pie-setup --project <raiz>`. Cada raiz guarda seu próprio `.pie/index.sqlite3`, configurações de cliente e identificação MCP. Consulte somente a raiz configurada. O MCP não aceita um argumento `root` por chamada; a raiz é definida ao inicializar o servidor. Para um segundo projeto, registre outro servidor de mesmo tipo associado à segunda raiz.

Exemplo:
```powershell
pie-setup --project "C:\dev\DoctorMesh"
pie-setup --project "C:\dev\AnotherProject"
```

O comando é idempotente: executar novamente não duplica entradas iguais. Ele **reindexa explicitamente** ao rodar o setup, mas as consultas normais ao servidor aquecido não chamam o indexador se os metadados dos arquivos não mudaram.

As pastas de configuração contêm caminhos locais absolutos. Revise antes de fazer commit de `.vscode/mcp.json`, `.mcp.json` ou `.codex/config.toml` em um repositório compartilhado. Não publique o banco `.pie/index.sqlite3` se ele contiver informações privadas do código.

## Diagnóstico de instalação e servidor

```powershell
python --version
pie --version
pie status --root "C:\dev\DoctorMesh"
pie search Model --root "C:\dev\DoctorMesh"
pie-mcp --root "C:\dev\DoctorMesh"
```

O último comando executa um servidor stdio e permanece aguardando mensagens JSON-RPC; **isso é esperado**. Encerre com Ctrl+C. Não imprima mensagens no stdout do servidor: o canal stdout é reservado ao protocolo MCP.

Para testar a comunicação, utilize **MCP: List Servers**, **Reset Cached Tools** se `pie_query` não aparecer depois de uma atualização, ou use o cliente de integração automatizado em `tests/test_pie_install_mcp.py`.

Se o Python instalado em um ambiente virtual mudar de caminho, atualize/revise as entradas MCP anteriores. O setup evita sobrescrevê-las sem consentimento; remova **somente a entrada do PIE correspondente** após salvar backup dos arquivos, e execute o setup novamente.

## Atualização e manutenção

```powershell
python -m pip install --upgrade "git+https://github.com/PauloDeAvila/Project-Intelligence-Engine.git@feat/pie-context-intelligence-v2"
pie index --root "C:\dev\DoctorMesh"
pie status --root "C:\dev\DoctorMesh"
```

Reinicie os servidores MCP ativos após atualizar o pacote. Reindexar manualmente é aconselhável depois de alterações em massa, migrações ou mudanças de regras de exclusão. Para monitorar mudanças em um terminal separado: `pie watch --root <projeto> --interval 5`.

## Diagnóstico por erro

| Sintoma | Possível causa | Recuperação |
| --- | --- | --- |
| `pie-setup` não encontrado | `Scripts` do Python fora do PATH | Execute `python -m pie.interfaces.setup --project <projeto>` |
| `index_state != CURRENT` | arquivo inacessível, muito grande ou erro de análise | Consulte `pie status`, corrija o diagnóstico, execute `pie index` novamente |
| `MCP root must be ...` | raiz inexistente, link simbólico ou não-diretório | Use uma raiz real local e indexável |
| `Source changed` / `STALE` | arquivo alterado depois do índice | `pie index --root <projeto>`; reinicie o servidor caso necessário |
| `Existing MCP registration conflicts` | registro já existe com outro comando/Python | Faça backup, edite apenas essa entrada e reprovisione |
| `ModuleNotFoundError: pie` | cliente executa outro interpretador Python | Compare o Python instalado com o caminho `command` do MCP |
| `pie_query` não aparece | cliente não recarregou ferramentas | Reinicie o MCP, redefina cache de ferramentas no VS Code e confira logs do cliente |
| `NOT_FOUND` | nenhum símbolo relevante encontrado | Refine a consulta, confirme indexação e suporte da linguagem |
| `AMBIGUOUS` | vários símbolos com mesmo nome | Refine usando nome qualificado/arquivo e confira evidências |
| `ECONNREFUSED` para 9Router | gateway de IA indisponível | Não afeta o servidor MCP local; teste o PIE separadamente |

Não elimine arquivos `.pie` ou configurações de outros clientes durante uma recuperação automática. Se for necessário reconstruir um índice corrompido, faça primeiro um backup de `.pie/index.sqlite3` e somente então reexecute `pie init` e `pie index` na raiz afetada.

## Segurança e limites

- Sem shell arbitrário via MCP e sem ferramentas de escrita no código-fonte pelo servidor.
- Consultas retornam evidências verificadas e indicam ambiguidades, relações não resolvidas e omissões.
- Diretório de acesso restrito à raiz do servidor; links simbólicos para fora são rejeitados.
- Os índices são específicos do projeto e persistem entre sessões.
- A configuração de MCP torna a ferramenta **disponível**, não obrigatória para qualquer modelo.
- Esta fase não é certificação de release 1.0, nem teste manual nos computadores dos usuários.

## Referências oficiais para formatos de configuração

- VS Code: https://code.visualstudio.com/docs/agents/reference/mcp-configuration
- Codex MCP: https://developers.openai.com/learn/docs-mcp
- Claude Code: https://code.claude.com/docs/pt/desktop
