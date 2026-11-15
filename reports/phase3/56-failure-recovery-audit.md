# Fase 3 — auditoria de recuperação da primeira falha A/B

## Resultado

`ROOT_CAUSE_UNRESOLVED`.

Nenhuma sessão Codex foi iniciada nesta auditoria. A primeira falha observável foi classificada como `TOOL_RESULT_FAILURE`: o item MCP `execute_blender_code` retornou `failed` depois de `get_addon_status` e `get_scene_info` concluírem com sucesso. O controlador então produziu a falha secundária `EXECUTOR_FAILURE` porque a evidência de rota não era válida.

## Execução recuperada

- Manifesto: `51-pilot-manifest.json`.
- Worktree: `C:\Users\phsra\AppData\Local\Temp\pie-phase3-pilot-530f8e1`.
- Commit do worktree: `1aef8e3`.
- Aplicativo/condição: Blender baseline.
- Tarefa: `blender-material-cert-v1`.
- `run_id`: `baseline-409e2a71803509b546248d24`.
- `pair_id`: `pair-d4b179952cf4570b9d7d97f7`.
- Comando externo terminou com exit code `1`.
- Foram consumidas `1/4` sessões; `3` não foram executadas.

## Linha do tempo

| Ordem | Servidor | Ferramenta | Estado |
|---:|---|---|---|
| 1 | blender | `get_addon_status` | completed |
| 2 | blender | `get_scene_info` | completed |
| 3 | blender | `execute_blender_code` | **failed — primeira falha** |

Mensagem sanitizada do executor:

```text
MCP route evidence failed; expected blender; observed blender/get_addon_status/completed;blender/get_scene_info/completed;blender/execute_blender_code/failed
```

O erro original produzido pelo provedor/upstream não está disponível. Portanto, não é possível distinguir entre rejeição do código enviado, erro do addon, erro de estado da cena ou resposta MCP inválida.

## Artefatos ausentes

O manifesto e a linha de comando externa foram preservados. Não foram encontrados JSONL do Codex, stderr interno, respostas MCP brutas, lifecycle correlacionado ou evento SQLite para esse `run_id`. O `capture_codex` original mantinha stdout/stderr apenas em memória e falhava antes de persistir um registro de uso.

Uma consulta somente leitura ao SQLite PIE não encontrou `baseline-409e2a71803509b546248d24`. Lifecycle de outras sondas não foi reutilizado porque não possui correlação por `run_id`/`pair_id`.

## Reprodução offline

- Gateway PIE: handshake e descoberta de ferramentas passaram.
- `execute_blender_code` com código somente de leitura passou pelo gateway.
- A cena atual contém `PIE_AB_Cube` e `PIE_AB_Material`.
- A falha Codex não foi reproduzida sem modelo.

Isso elimina o transporte PIE e a ausência básica da fixture como causas demonstradas, mas não prova a causa do código gerado pelo Codex.

## Correções aplicadas

- `ddc31cd`: prompt Blender com código de leitura determinístico.
- `ecd3158`: preservação de usage/metadados sanitizados em falhas de captura.
- `a76a651`: rejeição de manifesto cujo hash não corresponda ao cenário carregado.

Essas correções foram validadas offline. Elas não permitem afirmar que a falha original foi corrigida em runtime do Codex.

## Validação

```text
546 passed, 5 skipped, 133 subtests passed
```

Certificação: `NOT_CERTIFIED`.

Condição técnica para nova execução: novo lote explicitamente autorizado, sem retry da sessão histórica, com persistência prévia de metadados sanitizados, lifecycle e uso do provedor. O objetivo atual proíbe iniciar esse lote.
