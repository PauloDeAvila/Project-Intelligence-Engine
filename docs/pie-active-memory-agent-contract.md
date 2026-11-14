# PIE active memory and compact-context policy

This project uses PIE MCP as a source-aware context/memory helper.

1. Before nontrivial code or Blender work, check the project index via
   pie_tool_gateway project_status, then resume an explicit incomplete task
   if the current user request continues it. Do not reopen unrelated tasks.
2. Query source through pie_tool_gateway source_query, initially limited
   to five candidates and 2000-4000 output characters. Expand only if
   evidence is missing or ambiguous. Use proof packs for claims of impact.
3. At a meaningful milestone, use pie_task_start / pie_task_record for
   succinct decisions, checked references, test outcomes and next steps.
   Do not save entire chats, private keys, credentials or unverified claims
   as authoritative source facts. Do not checkpoint every minor operation.
4. In Blender, call pie_blender_scene_delta for the selected objects
   immediately before and after a relevant modification. INITIAL is a
   baseline; DELTA shows observed changes only. If PARTIAL or
   BUDGET_EXCEEDED, widen budget or use upstream native Blender inspection.
   UNCHANGED means the tracked fields match; it does not guarantee
   unchanged geometry, external textures, rendering or hidden state.
5. When the gateway returns PARTIAL, follow output_get using output_id
   and a bounded start offset. A recovered result may fail because the
   source changed: reindex and re-query instead of trusting it.
6. Do not claim cost reductions from character counts. Measure real
   input/output token use and accuracy on paired, independently reviewed
   tasks. Prefer correctness over fewer tokens when these conflict.
7. Run the full regression matrix and a separate PONTO.md review before
   describing an implementation as verified.

For Codex, configure the project-local MCP with:
pie-setup --project <absolute-project-path> --clients codex --tool-profile compact

The compact profile exposes five core tools instead of the entire
MCP catalog. It remains an opt-in feature; the default full profile
is backward compatible.
