# PIE Context Runtime — Fases 4–8

## Veredito

`PARTIAL_NOT_CERTIFIED` / `NOT_CERTIFIED`.

As rotas Codex → MCP → Blender/Web funcionaram e os oráculos válidos passaram. A economia geral não foi certificada: Web regrediu em tokens e Blender ainda não tem três pares válidos.

| Domínio | Pares válidos | Baseline | Optimized | Economia total | Latência optimized |
|---|---:|---:|---:|---:|---:|
| Blender v2 | 2 | 118.816 | 139.092 | **−17,065%** | **+20,236%** |
| Web v2 | 3 | 330.190 | 483.754 | **−46,508%** | **+11,114%** |

Os números são tokens reportados em `turn.completed` pelo provedor Codex, não estimativas por caracteres. O custo financeiro permanece `null`: não há tarifa verificada para `gpt-5.6-luna`.

## Blender

Os dois pares válidos passaram o oráculo JSON e usaram exatamente duas chamadas MCP por braço:

| Par | Baseline total | Optimized total | Economia | Input não cacheado | Latência |
|---|---:|---:|---:|---:|---:|
| R1 | 67.779 | 89.884 | −32,613% | 8.130 → 15.728 | +29,616% |
| R2 | 51.037 | 49.208 | +3,584% | 25.500 → 7.068 | +10,023% |

R3 e R4 foram rejeitados pelo oráculo no baseline: o modelo retornou `null` para tipo, localização e materiais. O optimized não foi iniciado nesses pares; não houve retry automático. Os registros e tokens dos failures estão preservados em `reports/phase4-8/codex-blender-default-cube-v2-baseline-r3-20261117.json` e `...-baseline-r4-20261117-record.json`.

## Web

Fixture usada: `http://127.0.0.1:8766/index.html`; nenhuma página externa foi acessada ou modificada. Cada braço fez quatro chamadas: navigate, snapshot, click, snapshot. Todos os seis oráculos passaram.

O resultado agregado é desfavorável: 483.754 tokens no PIE contra 330.190 no baseline. A entrada não cacheada também piorou: 39.574 → 51.080 tokens (**−29,075%** de economia). A redução de saída não compensou o contexto adicional.

## Implementação validada nesta retomada

- `d1b5710` — preflight aplica merge profundo dos perfis, preservando `command`/`args`.
- `991f44f` — falhas de oráculo/rota persistem o registro de uso do provedor.
- `35f055a` — allowlists normalizam ferramentas repetidas em sequências Web.

Índice PIE local: `CURRENT`, `workspace_match=true`, 280 arquivos, 2.285 símbolos, 2.650 imports, sem diagnósticos.

Suíte executada:

```powershell
$env:PYTHONPATH = "."
uv run pytest -q --basetemp .pytest-tmp-final-resume-pyroot
```

Resultado: **730 passed, 4 skipped, 126 subtests passed**.

Evidência JSON detalhada: [codex-phase8-resumed-20261117.json](C:/Users/phsra/OneDrive/Documents/ChatGPT/Korum/PIE-Clean/reports/phase4-8/codex-phase8-resumed-20261117.json).

## Pendências

1. Investigar por que o baseline Blender ocasionalmente gera campos `null` apesar de a ferramenta responder.
2. Obter um terceiro par Blender válido sem repetir tentativas já pagas.
3. Reduzir o contexto estrutural do gateway Web antes de alegar economia.
4. Manter `NOT_CERTIFIED` até a evidência melhorar; os resultados negativos permanecem incluídos.
