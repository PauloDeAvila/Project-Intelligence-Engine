# Blender real-fixture gate

Status: `PASS`.

The generator [generate_phase3_blender_fixture.py](../../tools/generate_phase3_blender_fixture.py) created a disposable Blender 5.3 `.blend` from [large_scene_spec.json](../../fixtures/phase3/blender/large_scene_spec.json). The live unsaved Blender window was not modified.

The independent validator [validate_phase3_blender_fixture.py](../../tools/validate_phase3_blender_fixture.py) checked 64 objects, 16 materials, the required object/material names, and passed the generated observation through the PIE compactor.

| Measurement | Result |
|---|---:|
| Source observation | 14,543 characters |
| Returned compacted observation | 3,806 characters |
| Compaction state | `PARTIAL` |
| SHA-256 | `525388fbd0e458c321015c0501e2b9e11ce337b97d2b18f704c4f019d5479425` |
| Model sessions | 0 |
| Quota consumed | No |

This proves the real Blender fixture produces a response large enough to activate compaction. It is not a token-savings result: provider usage is intentionally absent. The remaining gates are paid A/B parity, MCP correlation, and provider-reported usage.

Reproduction:

```powershell
$d = Join-Path $env:TEMP 'pie-phase3-blender-fixture'
New-Item -ItemType Directory -Force $d | Out-Null
& 'C:\Program Files\Blender Foundation\Blender 5.3\blender.exe' --background --python tools/generate_phase3_blender_fixture.py -- --spec fixtures/phase3/blender/large_scene_spec.json --blend (Join-Path $d 'large-scene.blend') --observation (Join-Path $d 'large-observation.json')
uv run python tools/validate_phase3_blender_fixture.py --root . --spec fixtures/phase3/blender/large_scene_spec.json --observation (Join-Path $d 'large-observation.json')
```
