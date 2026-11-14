# Fase 3.6 — causa-raiz MCP

## O que está provado

1. O gateway PIE consegue iniciar o upstream Blender, completar `initialize`, listar ferramentas e executar `get_scene_info` em processo direto.
2. O Blender está ativo e a porta 9876 aceita conexão.
3. O Codex carregou o servidor `pie-phase3-blender` e emitiu chamadas MCP para ele.
4. Nas duas execuções Codex finais, as ferramentas falharam; não há resposta textual de erro persistida.
5. O workspace divergente foi eliminado no par final: o preflight verificou `gateway_workspace=PASS`.

## O que não está provado

Não é possível distinguir, com os artefatos disponíveis, entre:

- sandbox do Codex impedindo o subprocesso ou a conexão local;
- lifecycle do servidor MCP no Codex encerrando o upstream cedo;
- condição de corrida na inicialização do `mcp-for-blender`;
- erro específico do adaptador de sessão Codex.

Os logs isolados do Codex não continham entradas textuais úteis. O oráculo fixo não fornece essa informação.

## Remediação aplicada

- Diagnóstico JSONL opcional via `PIE_MCP_DIAGNOSTICS_PATH`.
- Eventos de spawn, requests, `tools/list`, respostas, timeout, EOF, exit code e falhas de recovery.
- Diagnóstico sempre fora do stdout MCP.
- Overlays podem injetar o caminho de diagnóstico sem credenciais.
- Teste garante que stdout continua JSON-RPC e que o diagnóstico não contém payloads.

## Hipótese operacional restante

A hipótese mais forte é uma diferença entre o lifecycle/sandbox da sessão Codex e o processo direto, mas ela permanece hipótese. Não há base para declarar correção nem para retomar A/B.

## Resultado da chamada diagnóstica autorizada

A única tentativa instrumentada autorizada em 2026-11-14 falhou antes do spawn do gateway. O Codex rejeitou a configuração transitória com `invalid type ... expected a sequence` em `mcp_servers.pie-blender-optimized.args`. O erro foi causado pelo formato do override `-c` usado para essa tentativa; não houve eventos `gateway_constructed`, `upstream_spawn_start`, handshake, `tools/list`, `tools/call` ou `upstream_exit`. Este resultado é uma causa comprovada da tentativa diagnóstica específica, não da falha MCP original.

Estado causal: `INCONCLUSIVE` para a integração MCP original. A quota autorizada para a chamada diagnóstica foi consumida como tentativa operacional; não há uso reportado pelo provedor porque a execução terminou no parsing local.

## Próximo gate

O gate permanece fechado. Não deve haver nova tentativa automática: uma futura chamada diagnóstica exigirá nova autorização de quota e um profile/config overlay nativo, sem override `-c` de array. Só depois de observar `upstream_spawned`, `downstream_request`, resposta/timeout e `upstream_exit` no arquivo de diagnóstico será possível fechar a causa.
