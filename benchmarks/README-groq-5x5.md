# PIE NVIDIA 5x5 v2 — hard questions

This version replaces the identifier smoke test. The five prompts do not contain their expected answers and require reasoning about indexing, drift safety, graph semantics, the MCP contract, and reference integrity.

For each question the harness records separate MCP-retrieval latency, Groq API latency, input/output/total tokens, required-term scoring, and MCP JSON-RPC evidence. `without_pie` receives the complete source file; `with_pie` receives only the response from the relevant PIE MCP `pie_build_context` call (or `tools/list` for the protocol question).

Run locally:

```powershell
py -3 -m pip install openai
$env:NVIDIA_API_KEY = "<local secret>"
py -3 .\benchmarks\pie_nvidia_5x5.py --root . --output .\benchmarks\pie_nvidia_5x5_no_thinking_results.json
Remove-Item Env:NVIDIA_API_KEY
```

The harness uses NVIDIA's OpenAI-compatible endpoint and `nvidia/nemotron-3.5-super-vl-120b-a12b`. The approved run used `enable_thinking=False` and recorded 85.33% token savings, 5/5 WITH_PIE accuracy, and 5/5 WITHOUT_PIE accuracy. Evidence is preserved as compact labeled micro-blocks selected from MCP-returned source ranges; the evaluator checks independent facts rather than a single expected identifier. The API key is never written to the repository. This is a functional retrieval benchmark, not an autonomous model tool-selection benchmark: the harness invokes MCP explicitly so usage is independently verifiable.
