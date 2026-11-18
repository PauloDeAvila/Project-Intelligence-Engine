# Preflight de roteamento PIE — 16/11/2026

O backup de `C:\Users\phsra\.codex\config.toml` foi preservado com SHA-256
`d50272c8ba63760efdca22bd7731fa28cba3e8b81771ad33bcac163034e786b`. Apenas os
servidores `pie-blender-optimized` e `pie-web-optimized` foram apontados para
`PIE-Clean`; o servidor Blender original, `node_repl` e o outro servidor PIE
permaneceram inalterados.

O gateway Web foi inicializado diretamente a partir de `PIE-Clean` usando
Node.js com `@playwright/mcp@0.0.85`. `tools/list`, navegação, snapshot, clique
e `pie_web_context` passaram na fixture local; o marcador
`PIE_WEB_FIXTURE_V1` foi preservado.

O gateway Blender também inicializou a partir de `PIE-Clean` e anunciou 15
ferramentas, incluindo `get_scene_info` e `pie_blender_query_scene`. A conexão
com o processo Blender continua pendente por `WinError 10053`; nenhuma chamada
de cena foi executada e nenhuma alteração foi feita.

Certificação: `NOT_CERTIFIED` até o handshake real do Blender e os benchmarks
pareados Blender/Web serem concluídos.
