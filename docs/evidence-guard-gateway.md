# PIE Evidence Guard + local LM Studio Gateway (V1 preview)

This is a **preview branch**, not a V1 release. It exposes an opt-in, limited
certified Python-function workflow. It **does not** claim to verify arbitrary
natural-language explanations or arbitrary code behavior.

## What is supervised?

- `pie_verified_evidence(symbol=...)` returns a hash-verified canonical
  Python function signature and a bounded list of verified syntactic direct calls.
  It rejects absent, ambiguous or stale definitions.
- `pie-gateway` starts a local HTTP server with `GET /health` and
  `POST /ask`. The request explicitly supplies one Python symbol.
- The optional LM Studio request asks for a strict JSON claim proposal, which is
  checked field by field. **Only canonical PIE facts are rendered**. Model text
  is never inserted into the certified response.
- If the model's proposal is invalid, contradictory, unreachable or incomplete,
  `model_validation.status` is `REJECTED` and the canonical facts remain
  available. This is a deterministic fallback, *not proof the model self-corrected*.
- The gateway verifies the indexed source again after the model returns.
- The model is called at most once per /ask. There is no unbounded retry loop.
- Context, semantics, runtime effects and natural-language explanations **outside
  these exact fields are not certified**.

## Windows — isolated install

PowerShell:

```powershell
$Root = "C:\Users\phsra\OneDrive\Documents\Doctor Mesh"
$Venv = "$env:USERPROFILE\pie-evidence-gateway"
py -3.12 -m venv $Venv
$Python = "$Venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install "git+https://github.com/PauloDeAvila/Project-Intelligence-Engine.git@feat/v1-evidence-guard-gateway"
& $Python -m pie.interfaces.cli index --root $Root
& $Python -m pie.interfaces.gateway --root $Root --port 8766
```

Open another PowerShell window:

```powershell
Invoke-RestMethod "http://127.0.0.1:8766/health"

$Body = @{
  question = "Qual a assinatura de analyze_mesh e quais sao suas chamadas diretas?"
  symbol = "analyze_mesh"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8766/ask" -Method Post -ContentType "application/json" -Body $Body
```

The first mode has **no model dependency**. It proves the facts can be
retrieved, validated and rendered without LLM hallucinations.

## Enable LM Studio supervision

Start LM Studio's local API server, load your model and find its exact ID from
`http://127.0.0.1:1234/v1/models`. Restart the PIE gateway with:

```powershell
& $Python -m pie.interfaces.gateway --root $Root --port 8766 --upstream http://127.0.0.1:1234/v1 --model "<EXACT_MODEL_ID>"
```

Send the same `POST /ask`. Inspect these fields separately:

- `model_validation.status`: `VERIFIED`, `REJECTED`, or `NOT_REQUESTED`.
- `model_validation.checks`: exact-match or mismatch reason for each claim.
- `answer`: **always** rendered from fresh canonical evidence, never the
  model's unverified prose.
- `evidence`: structured source-backed provenance.

Try asking the model to invent a signature in the question; the public
`answer` must retain the actual indexed signature.

## Local MCP (for any client)

The MCP server exposes `pie_verified_evidence` with
`{"symbol":"analyze_mesh"}`. A plain MCP server **cannot intercept the
client's final free-text answer**. To supervise the final result, call the
Gateway HTTP endpoint from a controlled client or from the PowerShell commands
above. Do not misrepresent MCP output as end-to-end supervision.

## Security and scope

- The HTTP listener binds **only to 127.0.0.1**, with no external network
  listener; the optional LM Studio upstream must be a loopback HTTP URL.
- Requests require JSON, have size limits, and browser Origin headers are
  rejected. The gateway does not execute code in the indexed repository.
- There is **no user authentication**. Other programs running on the same
  computer can call the local endpoint; use only on a trusted local machine.
- Never expose the gateway through a tunnel, reverse proxy, public port-forward
  or untrusted multi-user host without a separate authentication layer.
- Only exact, unambiguous Python function names are supported in this preview.
  Duplicate names, missing or drifted source, unsupported queries, dynamic
  dispatch and uncertain relationships must not be reported as proven.

## Tests

```powershell
& $Python -m unittest discover -s tests -p "test_pie_evidence_gateway.py" -v
& $Python -m unittest discover -s tests -v
```

Run these test commands from a checkout of the repository branch, not from
an arbitrary directory after a pip-only install. For example:

~~~powershell
git clone --branch feat/v1-evidence-guard-gateway --single-branch https://github.com/PauloDeAvila/Project-Intelligence-Engine.git PIE-Evidence-Gateway
cd PIE-Evidence-Gateway
& $Python -m unittest discover -s tests -v
~~~

The test suite uses disposable Python fixtures and a fake model; it requires
neither Blender nor LM Studio. The real Doctor Mesh/Qwen benchmark, Windows
compatibility and security review are separate release gates.

## Model-facing correction semantics

The gateway does **not** claim to reason over arbitrary final prose. It can
reject structured mismatches with the canonical evidence and uses a deterministic
renderer to replace proposed factual text. This is the supported, testable
meaning of "automatic correction" in this preview.
