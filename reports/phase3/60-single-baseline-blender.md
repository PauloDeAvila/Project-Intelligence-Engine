# PIE Fase 3 — primeira execução reutilizável Blender baseline

## Resultado

`BASELINE_BLENDER_FAILED_ORACLE`

Esta foi uma única execução real do Codex, sem retry. O dispatch e o provider usage foram capturados, mas a verificação Blender independente encontrou valores diferentes do contrato; a execução não é reutilizável como braço baseline válido. Web e optimized não foram iniciados nesta operação.

| Campo | Evidência |
|---|---|
| Modelo | `gpt-5.6-luna` |
| Esforço | `medium` |
| Condição | `baseline` |
| Servidor MCP | `blender` |
| `task_id` / cenário | `blender-material-cert-v1` |
| `run_id` | `baseline-1c07733a5e3840e3ad9a9b79` |
| `pair_id` | `pair-81c43938155843a8bb299912` |
| Estado | `completed` / exit code `0` |
| Latência | `19.964,993 ms` |
| Chamadas MCP | `2` |
| Oráculo textual do Codex | PASS |
| Oráculo Blender independente | FAIL |

## Usage reportado pelo provedor

| Métrica | Tokens |
|---|---:|
| Entrada | 95.925 |
| Entrada em cache | 82.560 |
| Entrada sem cache | 13.365 |
| Saída | 672 |
| Reasoning informado | 150 |
| Total (`input + output`) | 96.597 |

`reasoning_output_tokens` não foi somado novamente ao total.

## Ferramentas observadas

1. `blender/get_scene_info/completed`
2. `blender/execute_blender_code/completed`

Nenhuma ferramenta fora da allowlist foi observada. A captura do baseline vem dos eventos JSONL do Codex; não é esperado evento de gateway PIE neste braço.

## Evidências

- Resultado do controlador: `60-single-baseline-blender-result.json`.
- Registro provider: `60-single-baseline-blender-result-record.json`.
- Ledger: `60-single-baseline-blender-result-budget-ledger.json`, estado `completed`, `consumed_sessions=1`, `remaining_sessions=0`.
- Captura forense: `C:\Users\phsra\AppData\Local\Temp\.pie-phase3-single-blender-ee107cd0331b480684414968ca174c21-pie-live-store\runs\baseline-1c07733a5e3840e3ad9a9b79\`.
- Artefatos presentes: `manifest.json`, `codex-events.jsonl`, `codex-stderr.log`, `mcp-tool-events.jsonl`, `provider-usage.json`, `oracle-result.json`, `run-result.json` e log sanitizado de stdout.
- O hash do answer coincide com o marcador textual esperado, mas isso não prova a cena.
- Leitura independente read-only posterior via Blender retornou `PIE_AB_Cube` / `PIE_AB_Material`, roughness `0.4000000059604645` e metallic `0.0`; o contrato exige `0.35` e `0.2`.
- A cena não foi alterada para mascarar a falha. O primeiro erro de aceitação é `INDEPENDENT_BLENDER_ORACLE_MISMATCH`.

## Comando reproduzível

```powershell
uv run python -m pie.certification.controller single `
  --scenario benchmarks/phase3/blender-certification-scenario.json `
  --application blender --condition baseline `
  --workspace <clean-temporary-worktree> `
  --baseline-home <temporary-baseline-home> `
  --optimized-home <temporary-optimized-home> `
  --baseline-profile pie-phase3-single-baseline `
  --optimized-profile pie-phase3-single-optimized `
  --output reports/phase3/60-single-baseline-blender-result.json `
  --timeout 240
```

## Próxima ação

Não executar optimized. Corrigir ou restaurar a fixture Blender de forma autorizada, gerar um novo par e repetir somente após o oráculo independente passar. Esta execução permanece evidência de dispatch/usage, mas está excluída de qualquer cálculo A/B.

Validação posterior do checkout: `uv run python -m unittest discover -s tests -q` — `564` testes passaram, `5` ignorados.
