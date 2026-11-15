# Fase 3.14 — preflight do HEAD atual

Foi criado um worktree Git temporário limpo no commit `75560b5`. O preflight foi executado sem iniciar o modelo:

| Cenário | Estado |
|---|---|
| Blender baseline | `READY_FOR_BENCHMARK` |
| Blender optimized | `READY_FOR_BENCHMARK` |
| Web baseline | `READY_FOR_BENCHMARK` |
| Web optimized | `READY_FOR_BENCHMARK` |

Para os braços optimized foi usado um overlay temporário contendo os mesmos gateways, com `--workspace` apontando para o worktree limpo. A configuração persistente do usuário permaneceu intacta. Nenhuma quota foi consumida.

O preflight do perfil optimized persistente, sem esse overlay, foi rejeitado por `PRECHECK_GATEWAY_WORKSPACE_MISMATCH`. Essa é uma condição obrigatória para a próxima bateria: cada profile optimized temporário deve apontar explicitamente para o worktree que será usado naquela repetição.

O ambiente está tecnicamente preparado para a bateria A/B, mas a certificação continua `NOT_CERTIFIED` até existirem três pares atuais com tokens, oráculos e evidência de rota correlacionada.
