# Codex Web A/B — par controlado real

Data: 2026-11-17  
Commit: `11c6d80c1db095820ec2a375c90d546a57b4e1cb`  
Par: `pair-codex-web-local-controlled-20261117`

## Resultado

O par controlado foi executado na mesma fixture local, no mesmo worktree limpo, com o mesmo prompt, modelo `gpt-5.6-luna` e esforço `medium`. Ambos os braços passaram pelo oráculo e executaram exatamente quatro chamadas MCP.

| Métrica | Baseline | Optimized / PIE | Variação |
|---|---:|---:|---:|
| Input tokens | 63.224 | 92.201 | **45,832% maior** |
| Input cacheado | 50.816 | 75.776 | 49,118% maior |
| Input não cacheado | 12.408 | 16.425 | 32,374% maior |
| Output tokens | 377 | 319 | 15,385% menor |
| Total tokens | 63.601 | 92.520 | **45,469% maior** |
| Latência | 18.481,357 ms | 18.485,529 ms | 0,023% maior |
| Chamadas MCP | 4 | 4 | 0 |

`reasoning_output_tokens` reportados: baseline 181, optimized 110. Eles permanecem separados e não são somados novamente ao total.

## Rotas e correção

- Baseline: `playwright-baseline`.
- Optimized: `pie-web-optimized`.
- Sequência em ambos: `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_snapshot`.
- O marcador `PIE_WEB_FIXTURE_V1` foi revelado e o oráculo passou nos dois braços.
- Nenhuma página externa foi acessada.

## Integridade do A/B

O baseline criou somente arquivos `.playwright-mcp` no worktree temporário. Esses artefatos foram verificados e removidos antes do optimized; o checkout voltou a ficar limpo. Assim, ambos os braços usaram o mesmo caminho de worktree e o mesmo commit.

## Veredito

`VALID_SINGLE_PAIR_NOT_CERTIFIED`.

Este par comprova que o gateway Web funciona e que a tarefa permanece correta, mas mostra **regressão de 45,469% nos tokens totais** nesta fixture. O resultado deve permanecer visível e impede afirmar economia Web genérica. A certificação geral continua `NOT_CERTIFIED`.

Evidência JSON: `reports/phase4-8/codex-web-local-controlled-pair-20261117.json`.
