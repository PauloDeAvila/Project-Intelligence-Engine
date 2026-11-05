# PIE NVIDIA 20x2 v3 — hard questions with rate limiting

This version uses twenty prompts that do not contain their expected answers. They cover indexing, scanner bounds, hashing, AST parsing, drift safety, graph semantics, resolver verdicts, references, Context Packs, MCP validation, and analysis integrity.

Each question runs once with PIE and once without PIE: 40 NVIDIA calls at most. Calls use `max_retries=0` and have a three-second minimum interval by default, so transient SDK retries cannot exceed the provider limit. The harness records separate MCP-retrieval latency, NVIDIA API latency, input/output/total tokens, independent fact scoring, and MCP JSON-RPC evidence. `without_pie` receives the complete source file; `with_pie` receives only compact evidence from the relevant PIE MCP call.

Run locally:

```powershell
py -3 -m pip install openai
$env:NVIDIA_API_KEY = "<local secret>"
py -3 .\benchmarks\pie_nvidia_5x5.py --root . --output .\benchmarks\pie_nvidia_20x2_results.json
Remove-Item Env:NVIDIA_API_KEY
```

Optional controls for a smoke run or a more conservative provider cadence:

```powershell
py -3 .\benchmarks\pie_nvidia_5x5.py --root . --output .\benchmarks\smoke.json --question-count 2 --delay-seconds 5
```

The harness uses NVIDIA's OpenAI-compatible endpoint and `nvidia/nemotron-3.5-super-vl-120b-a12b`. It keeps `enable_thinking=False`, the same concise answer contract, and independent fact checks so the larger question set does not trade quality for fewer calls. Evidence is obtained through the hash-backed `pie_build_proof_context` MCP tool, projected into a compact proof card for the model, and falls back to exact `pie_build_context` source lines when a requested obligation is not covered by an atom. The evaluator checks independent facts rather than a single expected identifier. The API key is never written to the repository. This is a functional retrieval benchmark, not an autonomous model tool-selection benchmark: the harness invokes MCP explicitly so usage is independently verifiable.
