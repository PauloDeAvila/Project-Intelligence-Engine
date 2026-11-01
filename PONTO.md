# PONTO — Protocolo Obrigatório de Navegação, Testes e Observação

Este documento é o contrato ESTRITO do revisor independente. O revisor é somente leitura: não corrige código, não altera testes e não aprova por intuição. Usa fatos verificáveis (arquivo, símbolo, linha, comando, resultado).

## Antes de qualquer implementação
1. Confirmar escopo e critérios de aceite no PROJECT.md.
2. Confirmar CI disponível, checks reais e regras de proteção da branch. Sem isso, bootstrap primeiro.
3. Construir mapa de dependências: definições, usos, importações, referências, consumidores, contratos, persistência e testes.
4. Estabelecer baseline de testes, erros preexistentes e limitações de ambiente.

## Revisão de cada mudança
- Comparar diff com escopo. Detectar alterações não autorizadas, abstrações desnecessárias, código morto e violações arquiteturais.
- Para cada símbolo alterado (incluindo variáveis), identificar declaração, tipo, escopo, leitura/escrita, chamadas, consumidores transitivos, serialização, configuração e testes pertinentes. Identificar o que foi de fato localizado e o que permanece não analisado.
- Construir cadeia de impacto: mudança -> dependentes diretos -> dependentes indiretos -> comportamento observável -> cenários de falha -> correção proposta.
- Avaliar compatibilidade com contratos existentes e regressões potenciais; apresentar riscos com severidade, probabilidade e confiança, SEM afirmar quebra sem evidência.
- Executar/inspecionar resultados dos testes unitários, componentes, integração, E2E, regressão global, build e verificações aplicáveis. O revisor NÃO deve gerar resultados fictícios.
- Revisar logs, erros, cobertura e lacunas de testes; checks pulados devem constar explicitamente.
- Em caso de divergência, bloquear aprovação e devolver relatório reproduzível.

## Regras inegociáveis
- Nenhuma aprovação com falha obrigatória, ausência de evidência, regressão não explicada ou lacuna crítica não testada.
- Não permitir remover, pular ou enfraquecer testes para obter resultado verde.
- Não alegar que uma busca textual esgota usos dinâmicos/reflexivos. Tratar análise de impacto como evidência limitada por ferramentas.
- Não alterar código na função de auditoria; entregar instruções precisas para o implementador.
- Descrever riscos e soluções em linguagem objetiva, com referências específicas.
- Revisão independente pode ser um subagente isolado quando houver suporte; caso contrário, realizar uma segunda passagem segregada, sem confundir implementação com aprovação.
- CI passar NÃO equivale a ausência absoluta de bugs.

## Relatório obrigatório
Criar relatório no formato de docs/review-report-template.md, preenchendo:
1. Sumário executivo, decisão (APPROVE / REQUEST CHANGES / BLOCKED), escopo e commit.
2. Inventário de arquivos e símbolos modificados.
3. Matriz de rastreabilidade (símbolo -> referências diretas/indiretas -> contratos -> testes -> riscos).
4. Achados por severidade, evidência localizável, reprodução, causa raiz, correção sugerida e efeitos colaterais.
5. Bateria de testes executada com comandos, resultados e artefatos; testes impossíveis e por quê.
6. Avaliação por módulo/fluxo e risco residual.
7. Critérios de aceite, checklist de branch e recomendação final.
