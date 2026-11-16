# Piloto real DeepSeek 3.2 — resultado pareado

Estado: `MEASURED_NOT_CERTIFIED`.

O relay local Infinity expôs `gambiarraapi/deepseek-v3.2`. O laboratório foi
executado em três tarefas do commit `3a109ccdffe5b2d0e30684a304fbd388e99ce57b`
do Textualize/Rich, com a mesma tarefa em baseline e PIE. O novo gate garantiu
que a evidência da resposta existia nos dois contextos antes das chamadas.

| Métrica | Baseline | PIE |
|---|---:|---:|
| Chamadas | 3 | 3 |
| Oráculo aprovado | 2/3 | 3/3 |
| Input tokens | 27.172 | 1.547 |
| Input cacheado | 1.393 | 822 |
| Input não cacheado | 25.779 | 725 |
| Output tokens | 389 | 150 |
| Total tokens | 27.561 | 1.697 |
| Latência mediana | 3,2684 s | 1,7992 s |

A redução observada seria `94,307%` em input e `93,843%` no total, com
`44,952%` de redução na latência mediana. Esses percentuais são apenas
observacionais: o baseline acertou 2/3 e o PIE 3/3, portanto a qualidade não é
equivalente e o par não pode certificar economia.

O resultado deve ser interpretado como evidência real de uso do provedor e uma
falha de paridade de qualidade do baseline. Nenhum prompt ou resposta completa
foi incluído no relatório versionado; os arquivos brutos permanecem locais
para auditoria controlada.
