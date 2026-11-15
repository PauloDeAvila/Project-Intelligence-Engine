# Fase 3 — diagnóstico da falha Blender

## Evidência sem consumo de quota

- Nenhuma sessão Codex foi iniciada nesta investigação.
- O gateway PIE completou `initialize` e `tools/list`.
- O gateway encaminhou `execute_blender_code` com código somente de leitura e recebeu `PIE_READ_ONLY_EXECUTE_PROBE`.
- A cena Blender contém `PIE_AB_Cube`, selecionado e ativo, com `PIE_AB_Material`.

## Conclusão

A falha do piloto não foi reproduzida no transporte local, no bridge PIE nem na pré-condição básica da cena. O ponto restante é específico do código enviado pelo Codex ou da resposta dessa chamada durante a sessão que falhou. A evidência do piloto continua fail-closed: não há tokens certificados dessa execução.

## Correção preparada

O cenário Blender passou a instruir o Codex a usar um corpo de código de leitura determinístico para `execute_blender_code`, preservando a tarefa, o estado e o oráculo. O manifesto anterior não foi reutilizado, pois seu hash de prompt ficou obsoleto.

## Validação

`14 passed` nos testes direcionados de controller e bridge. Nenhuma chamada de modelo foi executada. A certificação permanece `NOT_CERTIFIED`.
