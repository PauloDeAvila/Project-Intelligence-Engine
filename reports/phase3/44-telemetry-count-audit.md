# Fase 3.14 — auditoria da contagem de telemetria

Foi consultado em modo somente leitura o SQLite externo usado pelos imports de uso do provedor.

| Domínio | Baseline persistido | Optimized persistido | Pares estritamente certificáveis |
|---|---:|---:|---:|
| Blender | 3 | 3 | 2 |
| Web | 3 | 3 | 2 |

Os 18 registros persistidos comprovam que o coletor armazenou uso real do provedor, mas não transformam automaticamente todos os registros em pares válidos. A auditoria histórica exclui a repetição 1 por divergência de hash do prompt; além disso, os imports de uso não provam o roteamento de cada chamada MCP e foram capturados antes das correções finais do store de lifecycle.

Conclusão: a contagem do SQLite é maior que a contagem de pares certificáveis. O veredito permanece `NOT_CERTIFIED`.
