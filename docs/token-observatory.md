# PIE Token Observatory — experimental

Count any text payload, including serialized MCP, web, CLI and API responses:

```powershell
pie tokens --text "Hello" --model unknown
pie tokens --file original.txt --model gpt-4o
pie tokens --file original.txt --compare-file reduced.txt --model gpt-4o
```

`pie_count_tokens` exposes text-only estimates through MCP (string arguments limited to 4096 characters). Long documents should use CLI. `pie.telemetry.tokens.usage(response, provider="openai"|"anthropic")` normalizes **provider-reported** counts, including cache. Anthropic cached read/write values remain separate from input tokens. Estimates are **not billed usage** and exclude chat envelopes, hidden prompts, tool schemas, multimedia and other provider overhead.

Install optional `tiktoken` for supported model-tokenizer estimates. Otherwise use an explicitly labeled UTF-8 bytes / 4 heuristic. A Claude/Gemini tokenizer is never falsely treated as OpenAI-compatible. The comparison reports text savings, **not** accuracy or whole-session billing reduction.

Verification: `python -m unittest discover -s tests -v`, `python -m compileall -q src tools tests`, `python tools/verify_project.py`. Cross-check with actual API usage before reporting certified savings.
