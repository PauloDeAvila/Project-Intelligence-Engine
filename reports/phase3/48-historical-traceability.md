# Fase 3.15 — matriz de rastreabilidade das 12 execuções históricas

Fonte consultada em modo somente leitura: `C:\Users\phsra\.pie-global\projects\776668a48707658ebd7e41c78fc7d720\index.sqlite3`.

| Domínio | Braço | Repetições | Uso do provedor | Oracle | Rota correlacionada | Decisão |
|---|---|---:|---|---|---|---|
| Blender | baseline/optimized | 1 | disponível | hash divergente | não | `INSUFFICIENT_EVIDENCE` |
| Blender | baseline/optimized | 2–3 | disponível | passou | não | `INSUFFICIENT_EVIDENCE` |
| Web | baseline/optimized | 1 | disponível | hash divergente | não | `INSUFFICIENT_EVIDENCE` |
| Web | baseline/optimized | 2–3 | disponível | passou | não | `INSUFFICIENT_EVIDENCE` |

Resultado individual: `0 VALID`, `0 INVALID`, `12 INSUFFICIENT_EVIDENCE`.

Os tokens, latências e oráculos das repetições 2 e 3 são recuperáveis. O bloqueio restante é a ausência de `pair_id` histórico e de correspondência inequívoca entre cada import de uso e um evento lifecycle do gateway. A matriz completa está em `48-historical-traceability.json`.
