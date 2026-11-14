# Fase 3 — uso reportado pelo provedor

O coletor `live_codex` aceita somente `turn.completed` com `input_tokens`, `cached_input_tokens` e `output_tokens` inteiros não negativos. `uncached_input_tokens` é calculado como `input_tokens - cached_input_tokens` e `total_tokens` como entrada + saída.

O campo `reasoning_output_tokens` é preservado quando disponível no evento. Quando o provedor não entrega uso, o fluxo rejeita a certificação; não substitui ausência por zero. Os tokens do turno não são repartidos entre chamadas MCP.

Estado desta execução: `provider_usage_status = unavailable_for_certification`. Não foi executado um turno Codex real neste ambiente porque faltam configurações baseline/optimized verificáveis e os domínios de benchmark não estão disponíveis.

