# PIE Fase 3 — correção offline do roteamento dos perfis

## Resultado

`OFFLINE_FIXED`; dispatch real do Codex ainda `NOT_VERIFIED`.

`tools/prepare_phase3_profiles.ps1` gerava nomes `pie-phase3-blender` e `pie-phase3-web` nos dois overlays, mas o controlador e os manifests exigem:

| Condição | Blender | Web |
|---|---|---|
| Baseline | `blender` | `playwright-baseline` |
| Optimized | `pie-blender-optimized` | `pie-web-optimized` |

O gerador foi corrigido para alinhar os nomes sem alterar a configuração persistente do usuário nem os servidores originais.

## Verificação

Foi executado o gerador em diretório temporário e os dois TOML foram parseados com `tomllib`:

- baseline contém exatamente `blender` e `playwright-baseline`;
- optimized contém exatamente `pie-blender-optimized` e `pie-web-optimized`;
- baseline Blender não contém `pie.gateway.domain`;
- optimized Blender contém `pie.gateway.domain`.

Teste automatizado: `tests/test_phase3_profile_generation.py` — PASS.

Também foram copiados os overlays para dois `CODEX_HOME` temporários e executado `codex mcp list`. A CLI reconheceu exatamente:

- baseline: `blender`, `playwright-baseline`;
- optimized: `pie-blender-optimized`, `pie-web-optimized`.

O estado exibido foi `enabled`; `Auth=Unsupported` é esperado porque esses homes não continham credenciais e nenhum modelo foi iniciado.

Essa correção prova apenas a configuração dos perfis. Ainda falta uma sonda Codex real com aprovação compatível e captura forense válida; nenhum token foi consumido nesta etapa.
