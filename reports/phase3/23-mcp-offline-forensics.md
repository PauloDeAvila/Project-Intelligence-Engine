# Fase 3.7 — forense offline da integração MCP

## Escopo e restrições

Esta fase não executou `codex exec`, não consumiu quota, não alterou `config.toml` e não executou A/B. O índice PIE local da raiz do repositório está `CURRENT`, sem diagnósticos.

## Evidência da última sessão Codex

`reports/phase3/22-codex-mcp-probe-result.json` registra uma sessão real com exit code `0`, modelo `gpt-5.6-luna`, 136.207 tokens de entrada e 136.898 tokens totais. O Codex selecionou `pie-blender-optimized`, mas `get_addon_status` e `get_scene_info` terminaram com `failed`. O stderr continha somente avisos não fatais do Codex; não houve erro textual do MCP. Nenhum lifecycle JSONL foi criado.

Isso prova que o Codex chegou ao item MCP e tentou as ferramentas, mas não prova em qual processo a falha ocorreu. A ausência do arquivo é consistente com duas hipóteses: o processo MCP filho não herdou `PIE_MCP_DIAGNOSTICS_PATH`, ou o gateway encerrou/falhou antes de abrir o logger anterior.

## Auditoria do executor e configuração

O executor [run_codex_mcp_diagnostic.ps1](../../tools/run_codex_mcp_diagnostic.ps1) usa a configuração persistida, não usa `-c`, exige confirmação de uma chamada, não faz retry e grava somente metadados, stdout JSONL e stderr sanitizado. A rota persistida foi lida sem alteração:

```text
command: ...Project-Intelligence-Engine\.venv\Scripts\python.exe
args: -m pie.gateway.domain serve --domain blender --workspace <checkout> --max-chars 2400 -- <user>\.local\bin\uvx.exe mcp-for-blender
env keys: []
```

O ponto verificável é que a rota não declara `PIE_MCP_DIAGNOSTICS_PATH`; a tentativa anterior só colocou a variável no ambiente pai do Codex. O bootstrap agora não depende dessa herança: quando a variável está ausente, deriva `--workspace` de `sys.argv` e grava em `<workspace>/.pie-live-store/mcp-lifecycle.jsonl`.

## Bootstrap implementado

`src/pie/gateway/bootstrap.py` usa somente a biblioteca padrão, executa antes do import de `mcp_stdio`, escreve JSONL com flush imediato e nunca escreve no stdout MCP. `domain.py` registra falhas de importação e encerramento; `mcp_stdio.py` registra spawn, handshake/list/call recebidos e upstream.

## Matriz de hipóteses

| Hipótese | Estado | Evidência |
|---|---|---|
| Configuração persistida aponta para outro workspace | `REJECTED` | Args apontam para o checkout atual; probes offline usam o mesmo workspace. |
| Executável Python/`uvx` ausente | `REJECTED` | Ambos existem; `uvx 0.13.6` executa. |
| Blender indisponível | `REJECTED` | Porta `127.0.0.1:9876` em LISTEN; duas ferramentas passam offline. |
| Gateway/upstream incompatíveis | `REJECTED` no caminho offline | Spawn, initialize, tools/list e calls reais passam fora da sessão Codex. |
| Herança de ambiente Codex para o MCP | `CONFIRMED` como lacuna de observabilidade, não como causa única | Variável no pai não gerou lifecycle; config efetiva tem `env keys: []`. |
| Sandbox/lifecycle específico do Codex | `REJECTED` como causa primária do probe | Os erros do item MCP identificam explicitamente bloqueio de approval policy antes do dispatch. |
| Approval policy `never` | `CONFIRMED` | Os três `item.error` falhos dizem `MCP tool call requires approval, but approval policy is never`. |

## Comandos reproduzíveis sem modelo

```powershell
$env:PIE_PROBE_WORKSPACE=(Get-Location).Path
$env:PIE_MCP_DIAGNOSTICS_PATH="$env:TEMP\pie-phase37-offline\lifecycle.jsonl"
$env:PIE_BLENDER_PROBE_TOOL="get_scene_info"
uv run --project . python tools/probe_blender_domain_live.py

$env:PIE_BLENDER_PROBE_TOOL="get_addon_status"
uv run --project . python tools/probe_blender_domain_live.py
```

Ambos os comandos retornaram `state: PASS`, `handshake: true`, `tools_list: true` e `tool_call: true`.

## Validação do fallback sem ambiente

Após a correção, duas execuções offline sem `PIE_MCP_DIAGNOSTICS_PATH` explícito passaram. O arquivo padrão `C:\\Users\\phsra\\OneDrive\\Documents\\ChatGPT\\Korum\\Project-Intelligence-Engine\\.pie-live-store\\mcp-lifecycle.jsonl` acumulou 38 eventos: 19 para `get_scene_info` e 19 para `get_addon_status`. Ambas tiveram `upstream_exit=0`.

## Veredito da fase

`CODEX_MCP_PROBE_FAILED` para a sessão Codex real; `OFFLINE_MCP_INTEGRATION_PASS` para o gateway e upstream. A Fase 3.8 observou import, handshake e `tools/list` em dois gateways, mas nenhum `tools/call`; os erros do Codex confirmam bloqueio por `approval_policy=never`. O gate volta a `READY_FOR_CODEX_PROBE=false` até preparar uma alteração de aprovação explicitamente autorizada.

## Regressão Blender e suíte

As três falhas de retorno do Blender bridge foram corrigidas fazendo o bridge aguardar uma saída natural curta antes de terminar o upstream à força. O conjunto focado passou com `50 testes, 1 skip`. A suíte completa executou `541 testes, 5 skips` e apresentou uma falha intermitente de socket HTTP (`WinError 10053`) em teste não relacionado; a repetição isolada desse teste passou.
