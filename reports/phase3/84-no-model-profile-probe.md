# Probe sem modelo — perfis Blender

Estado: `BLOCKED_FOR_PAID_EXECUTION`  
Sessões de modelo: `0`  
Quota consumida: `0`

O perfil baseline completou `initialize`, `tools/list` e `tools/call` de `get_scene_info` diretamente no servidor Blender. O teste do marcador da fixture falhou porque a cena Blender atualmente carregada não contém `PIE_Large_Cube_00`; esse resultado não foi convertido em sucesso de oráculo.

O perfil optimized completou `initialize` e `tools/list`, expondo somente `pie_blender_query_scene`, mas a chamada retornou:

`PIE_QUERY_UNAVAILABLE: Blender did not return the expected scene query marker`

Isso bloqueia a validação do gateway seletivo contra a cena live atual. Não houve Codex, modelo ou consumo de quota.

O gateway real, sem modelo, listou somente `pie_blender_query_scene`. Uma chamada direta proibida a `get_scene_info` retornou `PIE_TOOL_NOT_EXPOSED` sem alcançar o upstream. O teste offline com upstream falso confirmou o mesmo bloqueio, e também confirmou que `structuredContent` é retornado junto com `content` para `pie_blender_query_scene`.

Evidência estruturada: [`84-no-model-profile-probe.json`](84-no-model-profile-probe.json).
