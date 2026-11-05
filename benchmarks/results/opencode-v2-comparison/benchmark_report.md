# Relatório de Diagnóstico — Benchmark PIE vs SEM PIE (Nemotron, OpenCode 2.2.5)

## Status

**BLOQUEADO** — A execução real do benchmark não pôde ser completada neste ambiente. O relatório abaixo documenta a causa raiz diagnosticada, as correções aplicadas e os próximos passos para execução.

## Cadeia alvo

```
Gateway PIE → OpenCode 2.2.5 → Nemotron → MCP do PIE → evidência verificável
```

versus

```
Gateway SEM PIE → OpenCode 2.2.5 → Nemotron (sem MCP do PIE)
```

## Problema identificado

O script `tools/run_pie_pair_windows.ps1` falhava com:

```text
RuntimeError: WITH_PIE server lacks connected pie MCP
```

Local: `tools/benchmark_opencode_pair.py` → `run()` → `_root_and_mcp()`.

## Causa raiz

Duas falhas combinadas:

1. **Race condition nas variáveis de ambiente**: O PowerShell `Start-Process` não transmite variáveis de ambiente (`OPENCODE_CONFIG`, `OPENCODE_PASSWORD`) de forma confiável para processos Node.js filhos (`opencode serve`). Como as duas instâncias eram iniciadas quase simultaneamente e as variáveis globais `$env:` eram reutilizadas, uma instância podia herdar a configuração da outra ou iniciar sem nenhuma variável.

2. **Verificação apenas da porta TCP**: O script original só verificava se a porta TCP estava ouvindo antes de prosseguir. O OpenCode 2.2.5 leva alguns segundos para iniciar o servidor stdio MCP do PIE e registrá-lo como `'connected'` no endpoint `GET /api/mcp`. A mera porta aberta não garantia que o MCP estivesse conectado.

## Correções aplicadas

| Arquivo | Alteração |
|---------|-----------|
| `tools/run_pie_pair_windows.ps1` | Cada instância OpenCode agora é iniciada via script `.bat` temporário que define `OPENCODE_CONFIG` e `OPENCODE_PASSWORD` isoladamente, evitando vazamento entre WITH_PIE e WITHOUT_PIE. |
| `tools/run_pie_pair_windows.ps1` | O script aguarda a conexão efetiva do MCP pie via `GET /api/mcp` (status `'connected'`) antes de iniciar o benchmark, não apenas a porta TCP aberta. |
| `tools/run_pie_pair_windows.ps1` | `WITHOUT_PIE` é verificado para não expor o servidor MCP `pie`. |
| `tests/test_benchmark_mcp_pair.py` | 6 novos testes de regressão cobrindo: MCP conectado aceito, MCP não conectado rejeitado, outro MCP (Doctor Mesh) rejeitado, raiz incorreta rejeitada, WITHOUT_PIE sem MCP aceito, WITHOUT_PIE com MCP rejeitado. |

## Resultado dos testes

```
Ran 146 tests in 6.827s
OK
```

- Total: 146 testes
- Aprovados: 146
- Falhas: 0
- Novos testes de regressão: 6 (`tests/test_benchmark_mcp_pair.py`)

Build check: `python tools/check_install.py` → PASS

## Evidência de conexão do MCP (teste isolado)

Quando o OpenCode 2.2.5 foi iniciado via script `.bat` com `OPENCODE_CONFIG` e `OPENCODE_PASSWORD` definidos, o endpoint `GET /api/mcp` retornou:

```json
{
  "location": {"directory": "C:\\Users\\phsra\\PIE-Benchmark-Test"},
  "data": [
    {"name": "9remote", "status": {"status": "connected"}},
    {"name": "pie", "status": {"status": "connected"}},
    {"name": "pie-doctor-mesh", "status": {"status": "connected"}}
  ]
}
```

Isso confirma que o MCP `pie` conecta corretamente quando o ambiente está configurado adequadamente.

## Bloqueio para execução real

Mesmo após as correções, a execução completa do benchmark não pôde ser rodada até o fim neste ambiente devido a:

1. Processos OpenCode pessoais do usuário ocupando portas TCP (4097, 4098, 43001, 50001, etc.).
2. Problemas intermitentes de passagem de variáveis de ambiente via PowerShell/cmd.exe.
3. Reinícios inesperados do servidor de execução durante o diagnóstico.

## Próximos passos

1. Liberar portas TCP dedicadas (ex.: `50001` e `50002`) sem processos OpenCode pessoais ocupando-as.
2. Executar:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\run_pie_pair_windows.ps1 `
  -PieRoot "$((Resolve-Path .).Path)" `
  -WithPort 50001 `
  -WithoutPort 50002 `
  -TimeoutSeconds 180
```

3. Confirmar saída: `WITH_PIE server with connected pie MCP` + `WITHOUT_PIE without pie MCP`.
4. Inspecionar `benchmarks/results/opencode-v2-comparison/results.json` para métricas reais (tokens de entrada/saída, latência, acertos, IDs de sessão, chamadas MCP).
5. Calcular a economia percentual de tokens apenas quando ambos os cenários fornecerem métricas comparáveis reais.

## Relatório de resultados (benchmark_results.json)

Não gerado: a execução real foi bloqueada. Não foram inventados resultados. Quando o benchmark for executado com sucesso, este arquivo será criado pelo próprio `benchmark_opencode_pair.py` na pasta `%LOCALAPPDATA%\\pie-bench-<guid>\\results.json`.

## Segurança

- Nenhuma credencial, senha, token de API, bearer token ou banco SQLite local incluído.
- Nenhuma instância pessoal do OpenCode foi modificada.
- O gateway público/Cloudflare não foi alterado.
- O PR permanece em Draft, sem merge na `main`.

## Commit publicado

- SHA: `9560bf3`
- Branch: `exp/opencode-remote-orchestrator`
- Mensagem: `fix(benchmark): restore PIE MCP connection and validate Nemotron comparison`
- PR: https://github.com/PauloDeAvila/Project-Intelligence-Engine/pull/39 (Draft)
