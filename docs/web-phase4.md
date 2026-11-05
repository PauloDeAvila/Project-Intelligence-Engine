# PIE Web Intelligence — Fase 4

## Escopo

A Fase 4 executa a peneira algorítmica entre o snapshot local e qualquer
futura entrega de contexto. Nenhum LLM, embedding, rede ou ação de navegador é
usado para pontuar ou reduzir candidatos.

Componentes:

- `RelevanceScorer`: score ponderado e explicável por cobertura textual,
  papel, região, visibilidade, habilitação e capacidade declarativa;
- `DecisionThresholdController`: limiar determinístico baseado em volume,
  orçamento e ambiguidade;
- `CandidateRanker`: ordenação estável por score, proteção, posição e ref;
- `RedundancyReducer`: remoção de duplicatas e corte por orçamento/quantidade;
- `WebRelevanceGate`: contexto quantificado com candidatos selecionados,
  omissões, custo estimado, limiar e possibilidade de expansão.

## Garantias

- Sinais de erro, alerta, segurança, senha e verificação são protegidos por
  um piso de relevância e não desaparecem apenas por falta de coincidência
  lexical.
- Omissões recebem somente códigos controlados (`below_threshold`, `budget`,
  `duplicate`, `limit`, `unsupported`); não há transcrição de texto no ledger.
- Snapshots `STALE` e `BLOCKED` são rejeitados.
- A redução não é autorização: `selected` continua contendo referências
  snapshot-bound e ações declarativas não executáveis.
- Contextos `PARTIAL` carregam `source_omitted_count` e
  `expansion_available=True` quando existe informação que pode ser recuperada.

## Desempenho

`tools/benchmark_web_relevance.py` mede 100 repetições aquecidas em fixtures
sintéticas de 64, 256 e 512 elementos. Na execução local Windows, o p95 foi
1,22 ms, 4,84 ms e 10,67 ms, respectivamente. Esta é a latência do gate local;
não inclui browser, rede, modelo ou serialização externa.

## Fora da fase

Política de segurança, aprovação humana, Evidence Packs, execução, cache
incremental e classificação semântica externa ficam para as fases seguintes.
