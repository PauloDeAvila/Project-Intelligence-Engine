# PIE V0.2 — implementação inicial (preview)

Este pacote é um **overlay** para o repositório `PauloDeAvila/Project-Intelligence-Engine`, branch `stabilize-v0-1`, commit-base `9e0cdda`. Não substitui a V0.1.

## Componentes

1. `src/pie/graph/relationships.py`: persiste em SQLite as chamadas sintáticas (`CALLS`, **unresolved**) e imports (`IMPORTS`, `verified` apenas quando o módulo local é localizado exatamente). Nunca afirma que uma chamada dinâmica foi resolvida.
2. `src/pie/retrieval/context.py`: pesquisa símbolos no índice e devolve trechos do código com hash verificado e limite de caracteres. Informa contexto omitido.
3. `src/pie/interfaces/mcp_server.py`: servidor MCP básico via stdio com `initialize`, `ping`, `tools/list`, `tools/call` e seis ferramentas.

## Instalação manual ou via Codex

Copie os arquivos do ZIP para a raiz do checkout da V0.1 preservando os diretórios. Não copie a pasta `shim`, que serviu apenas à validação isolada.

```powershell
python -m unittest discover -s tests -v
python -m pie init --root "C:\\caminho\\meu-projeto"
python -m pie index --root "C:\\caminho\\meu-projeto"
python -m pie.interfaces.mcp_server --root "C:\\caminho\\meu-projeto"
```

O terceiro comando iniciará o servidor e ficará aguardando mensagens JSON-RPC na entrada padrão; isso é esperado. Configure-o no cliente MCP com `python`, argumentos `-m pie.interfaces.mcp_server --root ...` e modo stdio, após instalar o pacote com `pip install -e .`.

## Teste direto do grafo e contexto

```python
from pathlib import Path
from pie.graph.relationships import build_relationships, get_relationships
from pie.retrieval.context import build_context
root = Path(r'C:\\caminho\\meu-projeto')
print(build_relationships(root))
print(get_relationships(root, 'App.run'))
print(build_context(root, 'App'))
```

## Limites expressos

- Python somente, análise de chamadas sintática, sem LSP/SCIP, despacho dinâmico ou grafo transitive avançado.
- O pacote não integra automaticamente comandos à CLI existente; as operações são acessíveis por Python e MCP.
- O Context Builder usa correspondência por nome, não busca semântica ou ranqueamento por dependências.
- Os testes locais do pacote usam um esquema SQLite reduzido compatível com as tabelas consultadas; é **obrigatório** executar a matriz completa no checkout real e a CI Windows/Linux antes de merge.
- A coleta de contexto considera o estado persistido e valida o hash de cada trecho. A validação da atualidade do grafo compara o fingerprint do índice armazenado.
- Não é uma release pronta para produção; revisão do protocolo MCP, isolamento de permissões e testes completos ainda são necessários.
