# Fase 3 — Pares reais iniciais

Os quatro registros abaixo foram capturados com `gpt-5.6-luna`, esforço `medium`, no commit `964f405`. Cada braço teve uso reportado pelo provedor, rota MCP verificada, oráculo aprovado e configuração distinta.

| Aplicação | Input baseline | Input optimized | Total baseline | Total optimized | Economia input | Economia total | MCP |
|---|---:|---:|---:|---:|---:|---:|---:|
| Blender | 58.346 | 45.073 | 58.734 | 45.450 | 22,749% | 22,617% | 1 → 1 |
| Web | 51.755 | 44.716 | 52.053 | 45.010 | 13,601% | 13,530% | 2 → 2 |

Todos os quatro oráculos passaram. O cache também foi registrado: Blender `46.080 → 39.552`; Web `42.880 → 39.296`. Custos permanecem `null`, pois não há tarifa verificada para `gpt-5.6-luna`.

Esses números são evidência real preliminar, não certificação. Falta completar dois pares por aplicação e repetir no HEAD após a correção de armazenamento externo do lifecycle (`6ce5afc`).
