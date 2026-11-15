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

O gate permanece fechado. Não deve haver nova tentativa automática: uma futura chamada diagnóstica exigirá nova autorização de quota e deverá usar [run_codex_mcp_diagnostic.ps1](../../tools/run_codex_mcp_diagnostic.ps1), que usa a rota persistida e não envia arrays por `-c`. Só depois de observar `upstream_spawned`, `downstream_request`, resposta/timeout e `upstream_exit` no arquivo de diagnóstico será possível fechar a causa.

## Resultado do probe corrigido

O executor nativo foi usado uma vez com a rota persistida. A sessão Codex terminou com exit code `0`, uso real reportado e seleção de `pie-blender-optimized`, mas `get_addon_status` e `get_scene_info` retornaram `failed`. Nenhum lifecycle JSONL foi produzido. Portanto, o probe é `CODEX_MCP_PROBE_FAILED`; a fase interna — spawn, handshake, upstream, timeout ou sandbox — permanece `INCONCLUSIVE`. O próximo diagnóstico deve configurar a variável de instrumentação no ambiente específico do servidor MCP, em vez de depender da herança do ambiente pai.

## Causa confirmada na Fase 3.8

Os três eventos `item.completed` falhos contêm a mesma mensagem sanitizada: `MCP tool call requires approval, but approval policy is never`. A configuração ativa do Codex usa `approval_policy = "never"`. O gateway chegou a `tools/list`, mas o cliente Codex bloqueou cada dispatch antes de enviar `tools/call`. A causa do probe é `CONFIRMED_CODEX_APPROVAL_POLICY`; não é uma falha demonstrada do Blender ou do upstream.
