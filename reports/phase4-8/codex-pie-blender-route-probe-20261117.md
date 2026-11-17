# Sonda Codex → PIE Blender

O Codex `gpt-5.6-luna` executou uma sessão somente leitura com esforço
`medium`. O roteamento foi comprovado: as duas chamadas observadas foram para
`pie-blender-optimized` e nenhum servidor proibido foi chamado.

- `get_addon_status`: falhou porque o addon Blender não estava conectado.
- `get_scene_info`: falhou pelo mesmo motivo.
- Tokens reportados: 137.115 entrada, 114.048 cacheados, 1.019 saída e 526
  reasoning.
- Cena modificada: não.
- Configuração persistente modificada: não.

O processo Blender não estava presente no host; havia apenas processos
`mcp-for-blender`. Portanto, esta evidência prova o roteamento Codex → PIE, mas
não prova a comunicação Codex → PIE → Blender nem economia oficial.
