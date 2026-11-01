# Primeiro prompt com PIE no Codex

Requisitos: Python 3.12+, cópia local deste repositório e um projeto de destino.

Execute na pasta local deste repositório:

```powershell
python -m pip install -e .
python tools/install_codex_mcp.py --project "C:\CAMINHO\MEU-PROJETO"
```

Reinicie o Codex na pasta do projeto. O instalador cria/adiciona uma seção `[mcp_servers.pie]` em `.codex/config.toml`, preservando as outras seções. Quando o Codex iniciar o MCP, `pie_mcp_bootstrap.py` inicializa e indexa o projeto antes de aceitar consultas. O código PIE permanece na instalação local; mover o repositório exige atualizar o caminho no arquivo de configuração.

No `AGENTS.md` do projeto, acrescente:

> Antes de alterações relevantes, consulte os recursos `pie_project_status`, `pie_find_definitions`, `pie_find_references` e `pie_build_context` via MCP. Interprete `probable` como hipótese estática, não verdade de execução. Se o índice estiver PARTIAL ou STALE, solicite reindexação antes de basear decisões nele.

Limitações: o PIE é predominantemente Python; não garante atualização durante a sessão após cada edição; a indexação é feita no início de cada processo MCP. É necessário fazer a instalação uma vez por ambiente/projeto. O registro/configuração do Codex precisa de teste no ambiente real antes de ser considerado compatível.
