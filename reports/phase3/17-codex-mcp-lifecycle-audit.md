# Fase 3.6 — auditoria do lifecycle MCP dentro do Codex

## Escopo

Auditoria sem chamadas de modelo. Foram comparados o registro efetivo do Codex, os overlays temporários, os caminhos de processo, o workspace, o Blender ativo, o probe direto e o gateway instrumentado.

## Configuração observada

| Item | Evidência |
|---|---|
| Branch | `feat/pie-phase3-task-telemetry-20261114` |
| Checkout auditado | `C:\Users\phsra\OneDrive\Documents\ChatGPT\Korum\Project-Intelligence-Engine` |
| CODEX_HOME | `C:\Users\phsra\.codex` |
| Modelo configurado | `gpt-5.6-luna` |
| Autenticação | `codex login status`: `Logged in using ChatGPT` |
| Codex executável | `codex-cli 0.169.0-alpha.11.1` |
| Sandbox da captura | `--sandbox read-only` |
| Timeout da captura | 240 s |
| Gateway timeout padrão | 120 s |
| Blender | Blender 5.3 ativo, porta 9876 LISTEN/ESTABLISHED |
| Rotas persistentes | `pie-blender-optimized`, `pie-web-optimized` |

O `codex mcp list` confirmou que os servidores PIE estão carregados. A configuração persistente aponta para o checkout principal; o par final falho usou overlays temporários com `--workspace` alinhado ao worktree, e o preflight confirmou `gateway_workspace=PASS`. Portanto, a divergência de workspace foi corrigida e não explica sozinha a falha final.

## Evidência de falha Codex

No par Blender final, os prompts e worktree foram equivalentes e o provedor reportou tokens, mas as chamadas MCP foram:

- baseline: `get_addon_status:failed`, `get_scene_info:failed`;
- optimized: `get_addon_status:failed`, `get_scene_info:failed`, `execute_blender_code:failed`.

O oráculo textual passou, mas é uma resposta fixa exigida pelo prompt; não substitui a execução bem-sucedida das ferramentas.

## Comparação direta

O probe direto do mesmo gateway/upstream passou handshake, `tools/list`, `get_addon_status` e `get_scene_info`. O Blender permaneceu ativo e a porta 9876 estava disponível. Isso delimita a falha à integração/lifecycle da sessão Codex ou às restrições de processo/sandbox, sem provar qual das duas.

## Privacidade

A instrumentação registra somente eventos, nomes de ferramentas, status, duração, PID, exit code e fingerprints. Não registra prompts, respostas, payloads, cookies, tokens de autenticação ou argumentos completos.

## Estado

`NOT_CERTIFIED` e não `READY_FOR_CODEX_PROBE`: a causa exata dentro da sessão Codex ainda não está demonstrada. O procedimento seguro para uma única chamada diagnóstica está preparado, mas não foi executado.
