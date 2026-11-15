# PIE Phase 3 — análise diferencial da regressão A/B

Esta análise usa somente os dois pares válidos já coletados. Nenhuma chamada de modelo foi
executada durante a análise.

## Resultado objetivo

| Métrica | Blender B/O | Web B/O |
|---|---:|---:|
| Input total | 58,889 / 111,291 | 66,027 / 66,475 |
| Delta input | **+52,402 (+88.98%)** | **+448 (+0.68%)** |
| Input cacheado | 35,840 / 94,336 | 56,704 / 56,832 |
| Input não-cacheado | 23,049 / 16,955 | 9,323 / 9,643 |
| Delta input não-cacheado | -6,094 (-26.44%) | **+320 (+3.43%)** |
| Output | 685 / 758 | 305 / 300 |
| Reasoning output | 209 / 211 | 151 / 119 |
| Total tokens | 59,574 / 112,049 | 66,332 / 66,775 |
| Delta total | **+52,475 (+88.08%)** | **+443 (+0.67%)** |
| Latência | 17,451 / 20,744 ms | 11,878 / 11,681 ms |
| Chamadas MCP | 2 / 2 | 2 / 2 |

## O que foi confirmado

1. **Chamadas adicionais não explicam a regressão.** Os dois braços fizeram exatamente duas
   chamadas, na mesma ordem e com as mesmas ferramentas esperadas.
2. **Reasoning não explica a regressão.** Blender teve apenas +2 tokens de reasoning; Web teve
   -32. O output Blender subiu 73 tokens, mas isso é muito menor que o delta de 52.475 tokens.
3. **A compactação não foi acionada.** O SQLite do gateway registrou:

   | Domínio | Ferramentas | Source chars | Returned chars | Estado |
   |---|---|---:|---:|---|
   | Blender optimized | `get_scene_info`, `execute_blender_code` | 208 + 151 = 359 | 359 | PASSTHROUGH |
   | Web optimized | `browser_navigate`, `browser_snapshot` | 410 + 414 = 824 | 824 | PASSTHROUGH |

   Em todos os eventos `source_chars == returned_chars`; portanto a economia de contexto foi
   zero nesses pares. O limite `max_chars=2400` não foi atingido.
4. **O gateway não criou trabalho de recuperação.** Não existem eventos `RECOVERY` nem chamadas
   adicionais no lifecycle ou SQLite.
5. **O efeito de cache foi diferente entre os domínios.** No Blender, o input cacheado optimized
   aumentou 58.496 tokens (+163,21%), enquanto o não-cacheado caiu 6.094. Na Web, o cache quase
   não mudou (+128), mas o não-cacheado aumentou 320.

## Interpretação causal permitida pelos dados

O aumento Blender é compatível com um prefixo/contexto maior no braço optimized, provavelmente
relacionado à descrição de ferramentas, metadados de servidor ou instruções do gateway. O
registro atual não contém a lista de ferramentas baseline nem o tokenizador do provedor aplicado
ao contexto, portanto não é correto afirmar que os 52.402 tokens sejam exclusivamente
descrições de ferramentas.

Na Web, o delta é pequeno e não há evidência de overhead de latência: a execução optimized foi
196,691 ms mais rápida. Ainda assim, como a compactação também não ocorreu, não há benefício de
contexto medido; o resultado total ficou 0,67% pior.

## Lacunas de medição

- O baseline original não passa pelo PIE, portanto não produz `source_chars`/`returned_chars`
  no SQLite. Esses campos só existem para o braço optimized.
- A captura forense preserva uso agregado do provedor, não o prompt completo nem o conteúdo das
  ferramentas, por política de privacidade. Não é possível decompor diretamente o input em
  “tool schema”, “system context” e “resposta MCP”.
- O lifecycle informa `tool_count=13` para Blender optimized e `tool_count=26` para Web
  optimized, mas não há uma medição equivalente dos servidores baseline nesta bateria.

## Próxima correção localizada recomendada

Antes de mudar o algoritmo de compactação, medir e reduzir o overhead do caminho optimized:

1. coletar `tools/list` baseline e optimized fora do Codex, sem modelo, registrando apenas
   contagem, nomes e tamanho de descrições;
2. comparar o schema agregado e identificar ferramentas PIE adicionais, especialmente a
   ferramenta de recuperação;
3. impedir que ferramentas não usadas pelo cenário sejam expostas no perfil da tarefa;
4. manter o comportamento `PASSTHROUGH` para respostas pequenas, mas evitar adicionar metadados
   de gateway ao contexto quando não houver redução real;
5. repetir primeiro um único par de validação após a mudança.

Nenhuma conclusão atual justifica declarar economia. O diagnóstico atual é: **Blender sofreu
principalmente aumento de contexto de entrada cacheado; Web teve pequena regressão de entrada
não-cacheada; nenhum domínio recebeu benefício de compactação nos pares observados.**
