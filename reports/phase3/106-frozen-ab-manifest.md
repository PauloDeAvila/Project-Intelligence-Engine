# PIE Fase 3 — manifesto A/B congelado

Estado: `BLOCKED_BY_QUOTA` para novas execuções e `NOT_CERTIFIED` para a economia geral.

O manifesto congela os cenários e o protocolo antes de qualquer nova autorização. O par Blender v3 já válido permanece preservado. Restam dois pares Blender e três pares Web: 10 sessões Codex.

| Domínio | Cenário | Pares válidos | Pares restantes | Gate sem modelo |
|---|---|---:|---:|---|
| Blender | `blender-selective-location-v3` | 1 | 2 | PASS |
| Web | `web-local-page-cert-v2` | 0 | 3 | PASS |

Ordens alternadas: baseline/optimized, optimized/baseline, baseline/optimized. Cada falha interrompe a bateria; retries permanecem desativados. O arquivo JSON é planejamento congelado, não autorização de consumo.

Evidências atuais: [`101-blender-v3-pair.json`](101-blender-v3-pair.json) e [`105-web-v2-no-model-gate.json`](105-web-v2-no-model-gate.json).
