# PIE Web Intelligence — Fase 3

## Escopo

A Fase 3 adiciona busca local sobre `PageSnapshot`, sem embeddings, rede ou
chamada a LLM. O índice é derivado, limitado e descartável; o snapshot continua
sendo a fonte de verdade.

Componentes:

- `CandidateExtractor`: normalização NFC, casefold e tokenização limitada;
- `RegionIndexer`: índices determinísticos por região e papel;
- `SemanticRoleMatcher`: vocabulário fechado de intenções comuns em português e
  inglês;
- `LocalWebSearch`: ranking local por cobertura textual, papel semântico,
  região, visibilidade e habilitação, com justificativas e ambiguidade explícita.

## Garantias

- Consultas são texto literal; CSS, XPath, `eval` e seletores não são aceitos
  como instruções.
- Snapshots `STALE` e `BLOCKED` não entram no índice.
- Elementos `UNSUPPORTED` ficam disponíveis apenas quando o chamador solicita
  explicitamente; não são confundidos com ausência.
- Colisões de `snapshot_id`, excesso de snapshots, resultados e termos falham
  de forma controlada.
- Empates próximos ou confiança baixa não são resolvidos silenciosamente:
  `SearchResponse.ambiguous` permanece verdadeiro quando aplicável.
- O ranking é reproduzível e ordenado por score, posição original e ref.

## Desempenho

`tools/benchmark_web_search.py` mede p50/p95/max em fixtures sintéticas de 64,
256 e 512 elementos, aquecidas e sem chamadas externas. O benchmark é uma
medição de busca local, não uma promessa de latência ponta a ponta do browser,
rede ou modelo.

## Fora da fase

Quantificação de relevância calibrada, redução de redundância, política de
segurança, Evidence Packs, execução, cache incremental e classificação externa
ficam para as fases seguintes.
