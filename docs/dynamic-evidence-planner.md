# PIE Dynamic Evidence Planner — DES-01 (experimental)

This **draft, isolated branch** adds an optional `dynamic_selection` mode to
the existing evidence-guard gateway. The `claims` and `evidence_selection`
modes are retained unchanged, and `main` is not modified.

## What this version actually does

1. An independently implemented **conservative keyword-based planner**
   classifies a question into supported static facts:
   `signature`, `path`, `line`, `direct_call_count`,
   `direct_call_sites`.
2. The model receives a **field catalog and evidence_id**, but NOT the
   planner's expected fields, the canonical fact values, or the gold answer.
3. Qwen proposes `{"evidence_id":"pie:...","selected_fields":["path","line"]}`.
4. The guard checks the exact evidence ID, schema, unique allowed fields,
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
