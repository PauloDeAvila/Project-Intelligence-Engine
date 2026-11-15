# Fase 3 — auditoria offline dos pares A/B

## Resultado

Os artefatos históricos contêm uso real reportado pelo provedor e quatro pares de repetições 2/3 com prompts e oráculos equivalentes. Eles são reutilizáveis como evidência preliminar de consumo, mas não certificam economia do PIE atual.

| Domínio | Pares preliminarmente comparáveis | Economia total observada | Estado |
|---|---:|---:|---|
| Blender | 2 | 13,628343% | Não certificado |
| Web | 2 | -12,372616% | Não certificado |

Os pares 1 foram excluídos por hashes de prompt diferentes. O Blender 4 foi excluído porque as ferramentas MCP falharam nos dois braços. Cada par 2/3 passou o oráculo e possui uso do provedor.

## Por que não são suficientes

- Os JSONs históricos não contêm nomes de ferramentas ou prova por execução de que o braço optimized atravessou o gateway.
- A persistência histórica registrou `0` observações de gateway Blender e `2` Web.
- As execuções históricas usaram o commit `dda927...`; o código do gateway mudou desde então.
- Portanto, os resultados medem consumo válido de sessões, mas não demonstram de forma completa a causalidade “PIE optimized → tokens observados”.

## Plano fechado

Para certificação no commit atual, são necessários **12 novos turnos Codex**: três pares Blender e três pares Web, seis baseline e seis optimized. Cada execução deve usar os perfis atuais, o mesmo prompt dentro do par, o mesmo estado local, o mesmo oráculo, telemetria do gateway e uso reportado pelo provedor.

Quatro chamadas seriam suficientes apenas se aceitássemos o commit histórico e a cobertura de rota incompleta; essa alternativa não atende ao critério de certificação atual.

Não foram executados modelos nesta auditoria. O estado permanece `NOT_CERTIFIED`.
