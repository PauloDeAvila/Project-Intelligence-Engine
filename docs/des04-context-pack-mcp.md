# DES-04 — Deterministic Context Pack (experimental)

The PIE Context Pack turns an indexed Python function or qualified method into a compact,
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
`symbol` (an exact unambiguous function name or qualified method such as
`MeasurementCache.get`). Optional arguments:
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
- `coverage`: verified direct call count within the current indexed scope,
  counts omitted by a caller limit and by the character budget; truncation
  is never silently represented as completeness
- `impact.status`: always `UNDETERMINED`; never a causal breakage claim
- `budget`: exact compact JSON character count; **not a token count**
- No model calls, code execution, or open-ended workspace path arguments

The package accepts exact unambiguous Python functions and qualified methods.
Qualified names match the stored lexical qualified name exactly (not a module
path or a suffix guess). Multiple matching definitions, including repeated
methods/property accessors, are refused. The signature and binding identify the
specific method; this does not infer the type of arbitrary instance receivers.
A future relevance planner or model-selection option must remain
a separate feature, benchmarked against this deterministic baseline.

### v2 coverage migration and resolver limits

`schema_version` is now `pie-context-pack-v2`. The misleading v1 field
`complete_direct_call_list` has been removed. Consumers must migrate to:

- `returned_verified_call_list_complete`: all **known verified** call sites
  were returned, with no omission by call limit or character budget.
- `static_analysis_coverage`: always `PARTIAL` for this analyzer.
- `exhaustive`: always `false`; even a zero-call result is not proof of no callers.

These fields are independent. Result completeness does not certify analysis
coverage. The static resolver does not exhaust dynamic dispatch, aliases,
reflection, unknown instance types or external/unindexed code. In particular,
`MeasurementCache.get` can have a verified definition but zero verified callers
while instance calls exist. Runtime impact remains undetermined.

Local imports now follow the same indexed import/re-export resolution as
module imports, with their lexical ownership and import provenance retained.
Local parameter/assignment shadowing is not promoted to an imported target.
Reads textually before a local import (including same-line reads and
comprehensions) and reads after a recorded name deletion are not certified.
Forward deferred closures may therefore remain unresolved. The analyzer does
not prove control-flow dominance, successful import execution, branch reachability
or absence of runtime rebinding/monkey patching; verified denotes a static
binding relation under the supported rules, not a runtime execution guarantee.

The analysis rules version is now 4. Reindex disposable working copies after
upgrading; older derived analyses fail closed until refreshed. Do not reindex
historical reference snapshots.

## Testing

```powershell
python -m unittest discover -s tests -p "test_des04_context_pack.py" -v
python -m unittest discover -s tests -p "test_des04_cross_module_resolution.py" -v
python -m unittest discover -s tests -p "test_static_call_coverage.py" -v
python -m unittest discover -s tests -p "test_des04_mcp_stdio_e2e.py" -v
```

The full CI should pass on Linux and Windows before review. A green test
suite establishes contract behavior on test projects, not universal
resolution completeness in arbitrary Python programs.

Historical DES-04 baseline artifacts remain unchanged. The Requests/Click
real-repository evidence probe is exploratory and not a frozen scored
benchmark.

Real-project validation can be repeated without indexing or modifying the originals:

```powershell
python tools/validate_static_context_projects.py --doctor-mesh "C:\path\to\Doctor Mesh" --requests "C:\path\to\requests" --output "C:\temp\pie-real-results.json"
```

This copies eligible Python bytes to temporary roots, indexes the copies, invokes
the actual MCP stdio process, checks source hashes before/after and records the
packs. Expected locations target the evaluated snapshots: six `audit_component`
calls including `capture.py:115` and `ui.py:627`, and six
`extract_cookies_to_jar` calls in Requests. Other revisions can legitimately fail
these location assertions; do not silently replace the reference expectations.
