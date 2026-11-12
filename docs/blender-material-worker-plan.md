# Blender Material Worker — implementation contract (proposal)

Status: initial implementation. A validated v1 Principled BSDF worker and offline unit tests are committed. Headless Blender execution is not yet certified.

## Goal

Keep PIE responsible for source-code discovery and evidence. Introduce a separate, local worker that receives a compact material specification, validates it, and applies a deterministic node graph through Blender's bpy API.

## Boundary

- Input: versioned JSON specification containing material name, shader type, scalar/vector parameters and optional texture paths.
- Validation: strict schema; reject unknown shader nodes, unsafe paths, invalid numeric ranges, and unsupported Blender versions.
- Execution: local bpy process, no arbitrary Python or shell from the model; resolve assets within an explicitly configured workspace.
- Output: material identifier, applied settings, warnings, provenance and deterministic fingerprint.
- Idempotency: same specification + Blender version + asset hashes yields the same material graph; avoid duplicate materials.
- Failure: preserve original material on validation failure; stage updates and roll back where feasible.
- PIE: indexes only worker Python source, not .blend contents. Never claim it indexes shader graphs without a separate adapter.

## Implementation milestones

1. Define and unit-test the JSON schema and canonical fingerprint independently of Blender.
2. Implement a bpy adapter behind a narrow interface, with fake adapter tests.
3. Add Blender headless integration tests creating and reopening a temporary .blend file.
4. Benchmark direct LLM-generated scripts versus short specifications with the same material quality gates and measured model tokens.
5. Add explicit opt-in MCP entrypoints; enforce local workspace boundaries and read-only default.

## Acceptance criteria

- No execution of model-provided code.
- Unit, integration, regression, and Windows compatibility gates green.
- Deterministic output and no duplicate materials on repeat requests.
- No unverified claims about token savings, render quality, or GPU acceleration.
- Separate PR for each milestone; no merge without CI evidence.

## Prototype usage

Create a JSON file such as:

```json
{"version":1,"materials":[{"name":"Steel","base_color":"#8899AA","metallic":1,"roughness":0.35}]}
```

Install the PIE package into Blender's Python environment or otherwise ensure `pie` is importable, then run:

```powershell
blender --background --python src/pie/blender/material_worker.py -- job.json --output result.blend
```

The worker refuses to overwrite an existing .blend file. It supports only a fixed Principled BSDF node graph and no arbitrary scripts, texture paths, or MCP interface. A real Blender headless test is still required before production use.
