# PIE × MCP for Blender — transparent stdio bridge (experimental)

The bridge is an **opt-in MCP stdio wrapper** around the unmodified
[ahujasid/mcp-for-blender](https://github.com/ahujasid/mcp-for-blender)
server, not an alternative Blender addon or a replacement for bpy. As of
2026-11-14, the upstream project calls its package mcp-for-blender
(previously blender-mcp). The server controls the live Blender addon;
PIE does not connect to the addon's TCP socket or bypass upstream
safety checks, consent/telemetry controls, asset integrations or tool schemas.

## What this actually guarantees

- Forwards JSON-RPC initialize, ping, resources, prompts, notifications,
  tool calls and unknown future methods to the upstream subprocess.
- Appends **one** local read-only tool, pie_blender_expand, to tools/list.
- Preserves native tools and their schemas. No arbitrary Blender code is
  interpreted or rewritten by PIE.
- Only intercepts large, successful, text-only responses from
  get_scene_info or get_object_info. Actions including
  execute_blender_code, import_asset and generation are never compressed.
- Never compresses an error, structuredContent, images or mixed-content
  outputs. Unknown tools pass through without alteration.
- Labels compacted outputs PARTIAL with a full source SHA-256 digest,
  original character count, omission count, compact preview, and
  pie_blender_expand recovery reference. Identical repeated large
  responses become UNCHANGED SHA references.
- The original full response is stored in a bounded, **process-local**
  32-response cache. pie_blender_expand retrieves exact chunks (up to
  16,000 characters) by response_id and start offset. Cache entries
  expire on eviction, server restart and interruption. If expired,
  query Blender again. There is **no durable Blender scene memory**.
- Results are length-budgeted in **characters, not tokens**. A lower
  payload size does not establish a measured reduction in LLM costs.

This provides protocol-level pass-through for nonintercepted operations;
it is **not a claim of 100% verified compatibility** with every Blender
MCP version, tool extension, client capability or installed Blender
addon. No real Blender GUI session was available in the CI tests.

## Windows / Codex setup

Install Python 3.12+ and the PIE repository locally:

~~~powershell
cd C:\dev\Project-Intelligence-Engine
py -3.12 -m pip install -e .
~~~

Install uv using its official instructions, install the Blender MCP addon,
and enable/launch the addon within Blender. The current upstream guide
uses:

~~~powershell
uvx mcp-for-blender install-addon
~~~

If you already have a Codex MCP entry named blender, **back up the existing
configuration** and replace only that specific registration after review.
Do not run two separate Blender MCP upstream servers against the same
addon port unless explicitly supported by your setup.

~~~powershell
codex mcp list
codex mcp add blender -- pie-blender-mcp --max-chars 2400 -- uvx mcp-for-blender
codex mcp list
~~~

The command is an example for a **new** Codex blender server entry. For an
existing entry, remove/rename that one via Codex configuration management
before adding the proxy. Keep the separate PIE source-code MCP configured
with pie-setup for project indexing; they serve different purposes.

You can run the wrapper directly for diagnosis:

~~~powershell
pie-blender-mcp --max-chars 2400 -- uvx mcp-for-blender
~~~

It waits for MCP JSON-RPC on stdin; seeing no normal stdout is expected.
All status/debugging information belongs on stderr to avoid corrupting MCP.

## Agent instructions (place in project AGENTS.md)

> Before changing a Blender scene, call upstream get_addon_status and
> get_scene_info as needed. Prefer scoped scene queries and small bpy
> operations; print only the necessary verification result from Python.
> If PIE returns PARTIAL, call pie_blender_expand to retrieve exact
> omitted detail before making any dependent decision. UNCHANGED means
> the source text has the same hash as an earlier observation in this
> running proxy, **not** that Blender cannot change between calls.
> Never treat a truncated preview as complete. Re-observe after writes
> and confirm the resulting scene. Respect user approval for destructive
> or external actions. For material workflows, prefer deterministic
> validated local worker specs when the separate worker is ready;
> do not claim this bridge implements the worker.

## Verification

~~~powershell
python -m unittest discover -s tests -p test_blender_mcp_bridge.py -v
python -m unittest discover -s tests -v
python tools/verify_project.py
python -m compileall -q src tools tests
~~~

A process-level stdio test uses a mock upstream Blender MCP, so no
Blender installation is required. Real-application acceptance additionally
requires the current Blender GUI, addon version handshake, Codex MCP
client integration, scene read/write/undo, images, error propagation,
multiple sequential sessions and realistic material tasks.

Compare the same work twice (native Blender MCP vs PIE bridge), using
the same version, scene, model and requested task. Record native tool
response characters, forwarded characters, model-reported input/output
tokens, total elapsed time, task completion, and visual/material
correctness. Report both p50/p95 and failure rates; never equate
character reduction to token reduction. Keep code execution restricted
to the upstream's selected safe mode and user-approved actions.

## Related implementation

The separate PR #62 introduces an early deterministic material worker.
Its current proposal/initial implementation is not automatically bridged
to all MCP for Blender tools, and Blender headless runtime certification
remains pending. This bridge must not claim to implement or certify it.
