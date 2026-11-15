# PIE Fase 3 — probe real Blender `structuredContent`

Data: 2026-11-15  
Commit do checkout: `cb1d1db`  
Estado: `PASS`  
Classificação: `PASSTHROUGH_SAFE`  
Certificação: `NOT_CERTIFIED`

## Ambiente

- Blender 5.3 GUI descartável, carregando `%TEMP%\pie-phase3-blender-fixture\large-scene.blend`.
- Porta MCP isolada: `9877`.
- Fixture: 64 objetos e 16 materiais; oráculo `PIE_Large_Cube_00` encontrado nos dois braços.
- Comparação feita sem `codex exec`, sem modelo e sem quota.
- A sessão Blender do usuário (`(Unsaved)`) não foi tocada.

## Contrato MCP observado

`get_scene_info` declarou `outputSchema`:

```json
{"type":"object","required":["result"],"properties":{"result":{"type":"string"}}}
```

O contrato exige o campo textual `result`. A resposta também contém `content[0].text` e `structuredContent.result`.

## Tamanhos reais

| Perfil | Resposta serializada | `result` | `content` | `content[0].text` | `structuredContent` |
|---|---:|---:|---:|---:|---:|
| Baseline upstream | 3.213 | 3.179 | 1.572 | 1.522 | 1.558 |
| PIE optimized | 3.213 | 3.179 | 1.572 | 1.522 | 1.558 |

Redução serializada: `0%`. O payload completo de cada braço, incluindo `initialize`, `tools/list` e `tools/call`, está preservado em [`79-real-blender-structured-probe.json`](79-real-blender-structured-probe.json).

## Duplicação e integridade

- `structuredContent.result` é `string` e é exatamente igual a `content[0].text` (`1522` caracteres).
- Hash do `structuredContent` baseline e optimized: `12ac4dccf110fbaea9291f16aa489adb3dfd8d0df1b7d6a972249b529c3588e6` — iguais.
- Hash de `content[0].text` baseline: `6c3aec1d27700d980df6fd748aaf5d9d06b4da52edd34ad4475ec94b811c42af`.
- Não houve conteúdo omitido, portanto não houve recuperação nem hash de recuperação aplicável.
- Uma chamada `get_scene_info` foi feita por perfil; não houve chamada duplicada.
- O oráculo da fixture passou nos dois braços.

## Veredito técnico

`PASSTHROUGH_SAFE` é a classificação correta. Como o `outputSchema` exige o texto completo e esse texto é duplicado em `structuredContent.result`, compactar somente `content` violaria a paridade do contrato ou deixaria o campo estruturado carregando o mesmo contexto integral. O PIE não remove `structuredContent` para fabricar economia.

Consequentemente, a compactação Blender ainda não está exercitada no caminho real do Codex. O A/B Blender não deve ser liberado como teste de economia até existir uma ferramenta/contrato resumido próprio ou uma resposta upstream cujo schema não exija a observação completa. Nenhuma economia de tokens é inferida a partir destes números de caracteres.

## Reprodução

```powershell
uv run python tools/probe_phase3_blender_structured_content.py `
  --workspace . `
  --python .venv\Scripts\python.exe `
  --uvx "$env:USERPROFILE\.local\bin\uvx.exe" `
  --output reports/phase3/79-real-blender-structured-probe.json `
  --max-chars 2400
```

O Blender descartável precisa ser iniciado com `tools/start_phase3_blender_fixture_gui.py`; `blender -b` é incompatível com o addon MCP, que reporta explicitamente que não inicia servidor em background.
