# Fase 3.14 — cruzamento final de cobertura de rota

Foi feito um cruzamento somente leitura entre os imports de uso do provedor e os arquivos `mcp-lifecycle.jsonl` ainda recuperáveis.

- Imports de uso do provedor: `12`.
- Arquivos lifecycle recuperáveis: `5`.
- Eventos de chamada Blender recuperáveis: `3`.
- Eventos de chamada Web recuperáveis: `5`.
- Correspondências por `run_id`: `0`.

Os eventos lifecycle comprovam que alguns probes atravessaram gateways, mas não permitem atribuir individualmente os 12 registros de tokens às execuções A/B. Portanto, a cobertura de rota permanece `INCOMPLETE` e o veredito permanece `NOT_CERTIFIED`.
