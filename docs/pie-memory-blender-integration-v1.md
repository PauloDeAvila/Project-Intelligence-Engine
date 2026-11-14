# PIE Memory + Blender Delta — operational runbook (2026-11-14)

Status: EXPERIMENTAL, stacked onto PR #63. These are changes in a feature
branch and do not constitute a release or a certified Blender deployment.

## 1. Memory and gateway integration

Previous work #29 / #30 / #31 / #32 was ported in dependency order,
retaining the current main branch MCP tools for source proofs and agent
Context Mesh. This introduces explicit persistent task checkpoints,
SQLite FTS5 task search, recoverable sanitized tool outputs and a
read-only operation-allowlisted Tool Gateway.

Local checkout commands:

~~~powershell
python -m pip install -e .
pie init --root C:\dev\MyProject
pie index --root C:\dev\MyProject
pie task-start --objective "Repair material" --root C:\dev\MyProject
pie task-record --task-id <task-id> --kind decision --text "Preserve BSDF" --root C:\dev\MyProject
pie task-resume --root C:\dev\MyProject
pie task-search "material" --root C:\dev\MyProject
~~~

MCP tools: pie_task_start, pie_task_record, pie_task_resume,
pie_task_search, pie_tool_gateway, pie_output_compact, pie_output_get.

Task notes are explicit user/agent-provided claims, not automatically
captured conversations or independently verified source evidence.

### Output retention, freshness and pagination

- 7-day expiry, maximum 128 output records and 8 MB stored UTF-8 content.
- Source-related gateway results store indexed source file SHA-256
  manifests; recovery checks live source hashes and rejects drift.
- Recovery through Tool Gateway operation output_get includes start
  offset, end offset and remaining characters with a hard response
  budget. Follow the returned end when state is PARTIAL.
- A sanitzed original remains available via its output_id until
  expiry/eviction. Expired handles must be recomputed, not fabricated.
- The redactor is best effort, not a secret scanner: never send keys.
- Retention applies to tool outputs, not durable task checkpoints.

Gateway sample arguments:

~~~json
{"operation":"task_search","arguments":{"query":"shader roughness"},"max_chars":2000}
~~~

## 2. Blender Delta Context

The Blender proxy now exposes pie_blender_scene_delta. It requests an
explicit, fixed, read-only bpy observation using the upstream Blender
MCP execute_blender_code implementation, without inventing a new
unrestricted execution channel.

~~~json
{"scope":"selected","max_chars":4000}
~~~

Observations include object transforms/visibility/material bindings,
material settings, shader-node types and input defaults, and node links.
Names, node graph data and settings receive deterministic SHA-256
fingerprints per scene + scope. The response is a bounded change report:

- INITIAL: first complete observation;
- UNCHANGED: exactly the same canonical observed snapshot;
- DELTA: added, removed or altered object/material entries;
- PARTIAL: incomplete/oversized observation; cannot prove absence;
- BUDGET_EXCEEDED: delta cannot fit the response budget, and previous
  full baseline is not advanced.

Manual edits are detected only upon the next explicit tool call, not
by a file watcher or persistent Blender history. The cache resets when
the proxy restarts. Use native Blender inspection for omitted data or
visual validation. No Blender headless or live GUI certification is
claimed by mock-upstream tests.

## 3. Three-arm actual token validation

Run fresh/restarted Blender scenes with identical scene checksum,
Blender version, model, hashed sampling settings, exact hashed task and independent correctness
oracle. The three conditions are:

- baseline: native Blender MCP without PIE.
- pie_current: existing PIE context MCP + native Blender MCP.
- pie_optimized: this branch with persistent memory, gateway and delta.

Store genuine provider-reported input/output token usage, elapsed wall
time, correctly graded outcome, scenario/repetition/model/scene and
oracle IDs. Model usage numbers must not be approximated as bytes/4.
Do not cherry-pick only successful tasks.

Put the data in a JSON file with records shaped like:

~~~json
{"records":[
 {"scenario_id":"example-task","repetition":1,"model":"model-id",
  "blender_version":"4.5.0","scene_sha256":"real-hash",
  "task_sha256":"real-task-hash","sampling_sha256":"real-settings-hash",
  "oracle_id":"review-id","condition":"baseline",
  "prompt_tokens":1200,"completion_tokens":200,
  "wall_ms":5000,"correct":true}
]}
~~~

Numbers in this example are schema placeholders, not measured results.
Provide all three conditions per task/repetition. Prefer 30 questions
times three repetitions; minimum acceptance gate is 10 complete pairs.

~~~powershell
python tools/certify_pie_blender_three_arm.py --input results.json --out summary.json --min-pairs 10 --strict
~~~

The gate rejects missing usage, incomplete/mismatched pairs, duplicate
measurements, accuracy regression and less than 85% measured paired
input-token savings. Even if it passes, its status is
MEASUREMENT_GATE_PASSED (external evidence review required), not
independent scientific certification. Missing data produces
NOT_CERTIFIED.

## 4. Deterministic validation

~~~powershell
python -m unittest discover -s tests -p test_pie_task_memory.py -v
python -m unittest discover -s tests -p test_pie_task_search.py -v
python -m unittest discover -s tests -p test_pie_memory_recovery_integration.py -v
python -m unittest discover -s tests -p test_pie_output_pipeline.py -v
python -m unittest discover -s tests -p test_pie_tool_gateway.py -v
python -m unittest discover -s tests -p test_blender_delta.py -v
python -m unittest discover -s tests -p test_blender_delta_stdio.py -v
python -m unittest discover -s tests -p test_pie_blender_three_arm.py -v
python -m unittest discover -s tests -v
python tools/verify_project.py
python -m compileall -q src tools tests
~~~

Follow PONTO.md for independent, read-only review and regression
verification. A real Windows/Blender GUI plus live Codex acceptance
must still check addon handshake, read-only safe-mode execution,
manual-edit delta, material graph behavior, rendering correctness,
and identical-task three-arm provider usage before production release.

For reduced tool-schema discovery in Codex, run: 

~~~powershell
pie-setup --project C:\dev\MyProject --clients codex --tool-profile compact
~~~

The compact tool profile is optional and offers only five MCP tools;
full profile remains the backward-compatible default. Configure a
fresh workspace or review/remove only the previous PIE registration
before changing an existing registration, since setup deliberately
refuses to overwrite mismatched MCP entries.
