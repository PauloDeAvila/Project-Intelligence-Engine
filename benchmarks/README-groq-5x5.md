# Groq 5x5 PIE benchmark

This benchmark runs five matched identifier questions against the same indexed checkout:

- `without_pie`: the complete source file is sent as context.
- `with_pie`: the local PIE MCP stdio server is called with `pie_search_symbols`, then only the exact matched symbol and a two-line source window are sent.

The Groq API key is read only from `GROQ_API_KEY`; it is never written to results. The MCP evidence records the tool name, query, response count, and a hash of the JSON-RPC output. The benchmark is a context-packaging comparison, not an autonomous model tool-selection test.

Run from the repository root:

```powershell
py -3 -m pip install groq
$env:GROQ_API_KEY = "<local secret>"
py -3 .\benchmarks\pie_groq_5x5.py --root . --output .\benchmarks\pie_groq_5x5_results.json
Remove-Item Env:GROQ_API_KEY
```

The checked-in validation run completed all 5 pairs: 5/5 correct in both conditions, 8,032 baseline tokens, 486 PIE-context tokens, and 93.95% token savings. This result depends on the compact, exact-symbol context policy; sending whole classes or modules can erase the savings.
