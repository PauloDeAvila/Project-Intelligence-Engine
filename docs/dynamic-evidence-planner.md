# PIE Dynamic Evidence Planner — DES-01 (experimental)

This **draft, isolated branch** adds an optional `dynamic_selection` mode to
the existing evidence-guard gateway. The `claims` and `evidence_selection`
modes are retained unchanged, and `main` is not modified.

## What this version actually does

1. An independently implemented **conservative keyword-based planner**
   classifies a question into supported static facts:
   `signature`, `path`, `line`, `direct_call_count`,
   `direct_call_sites`.
2. The model receives a **field catalog**, but NOT any evidence_id, the
   planner's expected fields, the canonical fact values, or the gold answer.
3. Qwen proposes `{"selected_fields":["path","line"]}`.
4. The Gateway binds the verified evidence ID internally; the guard checks schema, unique allowed fields,
   plus **relevance against the independent plan**.
5. Only after approval does PIE resolve and render the *actual source-backed
   values*; otherwise it returns `ABSTAIN` instead of pretending the model
   selected correctly.
6. Unsupported impact/runtime/exhaustive coverage questions, absent,
   ambiguous or stale symbols **abstain**. The current planner has limited
   rule coverage and is NOT a general understanding engine.

The gateway still revalidates project source after model inference.

## Windows isolated install

From an existing `pie-evidence-gateway\source` clone, fetch the branch without
touching your project index or overwriting local changes:

~~~powershell
$Base = Join-Path $env:USERPROFILE "pie-evidence-gateway"
$Source = Join-Path $Base "source"
$Python = Join-Path $Base ".venv\Scripts\python.exe"
$Root = Join-Path $Base "Doctor Mesh"

git -C $Source fetch origin feat/dynamic-evidence-planner-benchmark
git -C $Source switch -c feat/dynamic-evidence-planner-benchmark --track origin/feat/dynamic-evidence-planner-benchmark
# If the local branch already exists, use:
# git -C $Source switch feat/dynamic-evidence-planner-benchmark
# git -C $Source pull --ff-only

& $Python -m pip install --upgrade --no-deps $Source
& $Python -m unittest discover -s (Join-Path $Source "tests") -v
~~~

Stop the previous Gateway before starting the candidate. With LM Studio
running at `127.0.0.1:1234` and Qwen loaded:

~~~powershell
& $Python -m pie.interfaces.gateway --root $Root --port 8766 --upstream http://127.0.0.1:1234/v1 --model qwen3-4b-instruct-2507
~~~

In another terminal:

~~~powershell
$Body = @{question="Onde analyze_mesh está definida?"
          symbol="analyze_mesh"
          validation_mode="dynamic_selection"} | ConvertTo-Json -Compress
$Result = Invoke-RestMethod -Uri http://127.0.0.1:8766/ask -Method Post -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($Body))
$Result | ConvertTo-Json -Depth 10
~~~

Expected **shape**, not a promised live result: `status=CERTIFIED_FACTS`
and fields `path` and `line`, with no unrelated signature, if the Qwen
selects those two fields and passes independent relevance validation.

For unsupported questions, `status=ABSTAIN`; absence of an LLM call
must not be mistaken for an LLM successfully abstaining.

## Independent 30-question evaluation

The expert-authored gold test fixture has:
- 5 location questions
- 5 signature questions
- 5 caller/reference questions
- 5 combined-intent questions
- 5 impact/runtime questions that require abstention
- 5 out-of-scope questions that require abstention

Gold fields are **never transmitted to the model** by the benchmark.
The test suite tests the deterministic planner/guard with exact expected
outputs. For **real Qwen behavior**, execute:

~~~powershell
& $Python (Join-Path $Source "tools\benchmark_dynamic_selection.py") --output (Join-Path $Base "dynamic-selection-results.json")
~~~

It requests one `/ask` per unique case (30 total), saves the complete scored
JSON and exits non-zero if any case fails. Scores include exact field selection,
precision, recall, safe abstention and HTTP latency. The gateway does not expose
inference tokens, so token use is reported as **not measured**. These 30 questions
still concern only one symbol in one project: they are a benchmark gate, not
generalization or comprehension proof.

## Release conditions

Do not merge, tag 1.0 or change the default `claims` mode until:
- CI full regression Linux and Windows is green.
- Dynamic mode is compared with the two controls on the same question suite.
- The real Qwen results, latency, and failures are recorded.
- False positives, abstentions and ambiguous symbols are examined.
- Security and performance impact of rechecking the entire source snapshot is reviewed.

**Important:** PIE Gateway is an application API (`/ask`), not a transparent
OpenAI-compatible proxy and does not modify normal LM Studio chat.

## Follow-up after first real Qwen run (12/20)

The first 30-question integrated run achieved 12/20 positive selections and
10/10 safe abstentions, with seven of the eight positive failures caused by
Qwen copying the long evidence_id incorrectly. This branch revision changes
**only dynamic_selection**, so Qwen now emits just a list of selected field
names; the Gateway retains and revalidates its own trusted evidence handle.
No model-supplied identifier is accepted. The old `claims` and fixed
`evidence_selection` modes are unchanged.

This should be retested in the **isolated** environment before replacing the
existing gateway. This is a contract correction, not proof of an improved
selection score until a new real-model benchmark is run.

## DES-02: grammar-constrained dynamic selection (experimental A/B)

The second local Qwen benchmark measured **8/20** positive exact selections
and 10/10 deterministic safe abstentions. Ten positive failures had
`invalid_selection_shape`, and one additional response failed parsing.
The prior benchmark had 12/20 and is **not** evidence of semantic regression
until the raw shape differences are diagnosed. These statuses do not by
themselves reveal the original model text.

The new **opt-in** `dynamic_selection_schema` mode uses LM Studio's documented
`response_format.type=json_schema` to constrain generation to an object
containing exactly one key, `selected_fields`, whose array entries are enum
names from the catalog. It **does not** include the answer key (required fields),
source values, or any `evidence_id` in the model prompt or JSON Schema. PIE
continues to enforce the independent relevance plan and source verification.
The original `dynamic_selection`, `evidence_selection`, and `claims`
contracts are retained unchanged.

After updating the isolated candidate and restarting its Gateway in port 8766,
run both conditions against the same 30-case fixture:

~~~powershell
$Base = Join-Path $env:USERPROFILE "pie-dynamic-evidence-planner"
$Py = Join-Path $Base ".venv\\Scripts\\python.exe"
$Tool = Join-Path $Base "source\\tools\\benchmark_dynamic_selection.py"
& $Py $Tool --mode dynamic_selection --output (Join-Path $Base "des02-unconstrained.json")
& $Py $Tool --mode dynamic_selection_schema --output (Join-Path $Base "des02-schema.json")
~~~

Both commands write JSON reports even when their final exit status is nonzero
because some cases fail. Check the output files rather than interpreting a
nonzero benchmark exit as an HTTP transport failure. For model proposals that
fail structural validation, `model_validation.received_keys` lists only the
property names, not their untrusted values. This allows us to check whether
unexpected `evidence_id` fields are a frequent cause without leaking content.

LM Studio structured JSON may not work reliably with all small local models.
The point of this experiment is to measure that compatibility **without
weakening the downstream guard**, not to declare success in advance. Abstention
cases are screened by deterministic rules and may never call the model.
