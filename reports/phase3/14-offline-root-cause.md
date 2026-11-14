# Fase 3.5 — investigação offline

## Escopo

Esta análise usou somente os 12 registros sanitizados já coletados, os overlays TOML temporários, o SQLite local e o código atual. Nenhuma chamada de modelo foi executada.

## Causas confirmadas

1. Os pilotos da repetição 1 não são pares válidos: os hashes de prompt baseline/optimized diferem em Blender (`5f8d...`/`5fdc...`) e Web (`9ced...`/`14a1...`). As repetições 2 e 3 usam o mesmo hash.
2. O overlay optimized continha `--workspace` apontando para o checkout principal, enquanto o Codex foi executado em worktree temporário. Isso torna a raiz de armazenamento/detecção do gateway diferente da raiz auditada pelo runner e explica a cobertura SQLite incompleta.
3. A regressão Web está concentrada na repetição 3: 272.287 tokens de entrada optimized contra 202.275 baseline, cinco contra quatro eventos MCP e latência 25.167,380 contra 21.242,227 ms.

O último ponto é uma correlação observada, não uma atribuição causal fechada: os registros não guardaram os nomes das ferramentas nem os tamanhos por resposta.

## Resultado por repetição

| Domínio | Repetição | Pareável | Economia input | Economia input não cacheado | MCP B/O |
|---|---:|---:|---:|---:|---:|
| Blender | 1 | não | 9,241% | não calculada para certificação | 3/2 |
| Blender | 2 | sim | -4,258% | -7,732% | 2/3 |
| Blender | 3 | sim | 30,132% | 9,294% | 2/2 |
| Web | 1 | não | 14,750% | não calculada para certificação | 3/3 |
| Web | 2 | sim | 17,107% | 2,174% | 4/3 |
| Web | 3 | sim | -34,612% | -28,504% | 4/5 |

## Limitações

Os registros antigos armazenaram apenas `tool_events`; não é possível reconstruir offline quais ferramentas MCP foram usadas, se houve recuperação paginada ou se cada evento atravessou o gateway. A nova captura passa a registrar apenas `server`, `tool` e `status`, sem payloads sensíveis.

## Próxima correção

Gerar o overlay optimized por worktree, com o caminho de `--workspace` igual ao workspace efetivamente passado ao Codex. Depois, solicitar nova autorização somente para os pares faltantes. O estado permanece `NOT_CERTIFIED`.
