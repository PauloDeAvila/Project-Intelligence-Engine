# Blender evidence agent — constrained local integration test

Previous exact replay: the MCP returned the correct object name but Qwen3:4B
altered PIE_Large_Cube_00 to PIE_Large_Cube_0:00 during transcription.
Source-only rendering had passed the probe, but not the model oracle.

This new *independent* experiment has the following contract:

1. Read the enabled tool catalog from the real Blender MCP
2. Ask local Qwen3:4B to choose two integers: tool_index and target_index
3. Fail closed on invalid indices or tool allowlist, without retries
4. Invoke the one selected, read-only MCP tool
5. Render canonical values directly from the MCP response, not from model text
6. Check the result against an independent answer oracle
7. Count actual Ollama planning input/output tokens

No object names, material names, or other exact values are generated as
final prose by the model. The expected_exact gold value is used ONLY for
independent post-execution evaluation and never sent to the model.

Scope: one available tool and one fixed fixture object per arm. This
demonstrates the integration boundary, but does NOT demonstrate meaningful
multi-tool planning or general agent autonomy. It measures *planning tokens*,
which are not comparable to earlier model-copying token totals.

## Windows execution

Prerequisites: experimental worktree, disposable Blender 5.3 fixture on port
9877, local Ollama with qwen3:4b, uv preferred.

~~~powershell
git fetch origin feat/pie-local-ollama-mcp-benchmark
git merge --ff-only origin/feat/pie-local-ollama-mcp-benchmark

.\tools\run_blender_evidence_agent.ps1 -Model qwen3:4b -NumCtx 8192 -Repetitions 1
~~~

If the first pair passes and repetitions are desired:

~~~powershell
.\tools\run_blender_evidence_agent.ps1 -Model qwen3:4b -NumCtx 8192 -Repetitions 3
~~~

Outputs are write-once under the Windows temporary directory and have
the prefix pie-blender-evidence-agent-. Stop after the first invalid plan,
failed MCP tool or failed independent oracle.

Metrics: plan_valid, oracle_pass, usage.input_tokens/output_tokens,
savings_percent for planning tokens only, answer_sha256 for exact source
facts, MCP wall time, model planning wall time, and one MCP call per arm.

Tests without calling Blender, Ollama or Codex:

~~~powershell
uv run python -m unittest discover -s tests -p test_blender_evidence_agent.py -v
~~~

No paid Codex sessions are started. The official frozen protocol 106/107
is untouched. Codex certification remains NOT_CERTIFIED.
