# Plano de validação dos pares faltantes

Os registros existentes têm dois pares comparáveis por domínio (repetições 2 e 3). Para atingir o mínimo de três, falta somente uma repetição comum por domínio: quatro chamadas no total.

O executor [run_phase3_missing_pair.ps1](../../tools/run_phase3_missing_pair.ps1) é deliberadamente limitado a duas chamadas por cenário, sem retries, e exige `-ConfirmQuotaUse I_UNDERSTAND_2_MODEL_CALLS`.

Pré-condições:

1. Criar overlays com `prepare_phase3_profiles.ps1` para o mesmo worktree usado pelo Codex.
2. Validar ambos os perfis com `pie-live preflight`.
3. Confirmar autenticação, cenário, oráculo e upstreams.
4. Obter nova autorização para quatro chamadas Codex.

Executar uma vez para o cenário Blender e uma vez para o cenário Web, usando `-Repetition 4` e os perfis explicitamente nomeados. Depois, combinar os quatro registros novos com as oito capturas estritamente comparáveis existentes e executar o comparador com `--min-pairs 3`.

Nenhuma chamada foi executada ao criar este plano. O estado permanece `NOT_CERTIFIED`.
