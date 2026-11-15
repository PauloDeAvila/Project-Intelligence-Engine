# Fase 3.17 — piloto A/B interrompido

## Resultado

`AB_PILOT_FAILED`.

O controlador iniciou somente a primeira sessão autorizada: Blender baseline, repetição 1. O preflight dos quatro braços havia passado com `READY_FOR_BENCHMARK`, mas a sessão real fez três chamadas:

| Servidor | Ferramenta | Estado |
|---|---|---|
| `blender` | `get_addon_status` | `completed` |
| `blender` | `get_scene_info` | `completed` |
| `blender` | `execute_blender_code` | `failed` |

Como havia uma chamada inesperada com falha, o controlador rejeitou a evidência e interrompeu imediatamente. O usage do provedor não foi persistido pelo caminho fail-closed; não há tokens certificados para esta execução.

## Orçamento

- Autorizadas: `4`.
- Consumida: `1`.
- Não executadas: `3`.
- Retries: `0`.
- Lote complementar: não executado.

Nenhuma sessão Web foi iniciada. Nenhuma configuração persistente ou servidor original foi alterado. O detalhamento sanitizado está em `52-pilot-failure.json`.

Certificação: `NOT_CERTIFIED`.
