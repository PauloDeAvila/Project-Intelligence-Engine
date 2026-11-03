# DES-04 — Deterministic Context Pack (experimental)

The PIE Context Pack turns an indexed Python function into a compact,
source-backed packet for coding assistants. **It is not a runtime impact
certificate.** It uses the existing strict `build_evidence` contract, so a
stale inventory, an ambiguous function name, or a truncated 500-row reference
lookup causes a refusal rather than a deceptively complete answer.

## Local CLI

Run against an **already initialized/indexed** project (do not point this
command at the historical baseline snapshots):

```powershell
pie context-pack extract_cookies_to_jar --root "C:\\path\\to\\project" --max-chars 12000 --max-calls 100
```

Or without an installed shell entrypoint:

```powershell
python -m pie.interfaces.cli context-pack extract_cookies_to_jar --root "C:\\path\\to\\project"
```

Reindex your project's working copy after installing the resolver update:

```powershell
pie index --root "C:\\path\\to\\project"
```

## MCP (existing stdio server)

The existing `pie-mcp` process now advertises the tool
`pie_build_context_pack` through `tools/list`. Required argument:
`symbol` (an exact unambiguous function name). Optional arguments:
`max_chars` (1500–64000, default 12000) and `max_calls` (1–100,
default 100). The server receives the project directory only from its
**trusted launch configuration**, not from model-supplied tool arguments.

```json
{"name":"pie_build_context_pack","arguments":{"symbol":"extract_cookies_to_jar","max_chars":12000,"max_calls":100}}
```

The `pie-mcp --root ...` server must run with a trusted absolute project
directory. Configure that process using the appropriate Codex/Claude MCP
configuration for your installation. Avoid sharing the stable Gateway's
working port with the MCP process (stdio uses no TCP port).

## Contract

- `definition`: exact function location, signature, indexed SHA-256,
  stable binding key and optional bounded line-numbered snippet
- `callers`: proven static direct calls, with source path, line, consumer
  symbol, indexed source hash and target binding
- `coverage`: exact direct call count within the current indexed scope,
  counts omitted by a caller limit and by the character budget; truncation
  is never silently represented as completeness
- `impact.status`: always `UNDETERMINED`; never a causal breakage claim
- `budget`: exact compact JSON character count; **not a token count**
- No model calls, code execution, or open-ended workspace path arguments

The package intentionally covers only exact unambiguous Python functions at
this stage. A future relevance planner or model-selection option must remain
a separate feature, benchmarked against this deterministic baseline.

## Testing

```powershell
python -m unittest discover -s tests -p "test_des04_context_pack.py" -v
python -m unittest discover -s tests -p "test_des04_cross_module_resolution.py" -v
```

The full CI should pass on Linux and Windows before review. A green test
suite establishes contract behavior on test projects, not universal
resolution completeness in arbitrary Python programs.

Historical DES-04 baseline artifacts remain unchanged. The Requests/Click
real-repository evidence probe is exploratory and not a frozen scored
benchmark.
