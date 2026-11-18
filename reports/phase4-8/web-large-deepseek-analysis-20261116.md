# Web grande — resultado DeepSeek

## Gate do gateway

O snapshot bruto da fixture tem 8.632 caracteres. O gateway devolveu 2.164
caracteres (`PARTIAL`) e manteve recuperação disponível: redução de observação
de 74,93%. Isso comprova o caminho de dados, não economia de tokens.

## Tentativas de modelo

Foram feitas três tentativas manuais, sem retry automático. Todas falharam no
oráculo independente e foram excluídas de qualquer certificação:

| Execução | Baseline | PIE | Economia nominal | Falha |
|---|---:|---:|---:|---|
| Cap inicial | 10.518 | 6.912 | 34,284% | baseline atingiu limite; resposta PIE inválida |
| Cap 512 | 10.288 | 6.953 | 32,416% | ambos copiaram marker no campo status |
| Prompt esclarecido | 10.928 | 6.933 | 36,557% | baseline tentou `browser_evaluate`; PIE omitiu marker |

Os percentuais acima são somente diferenças nominais entre execuções inválidas.
Não são economia certificada.

Evidências detalhadas: os três JSONs `web-large-deepseek-ab-*.json` deste
diretório.

## Veredito

`PILOT_INVALID_QUALITY`: a compactação Web funciona, mas a tarefa ainda não
passa pelo agente DeepSeek com correção equivalente. O estado geral permanece
`PARTIAL_NOT_CERTIFIED`.
