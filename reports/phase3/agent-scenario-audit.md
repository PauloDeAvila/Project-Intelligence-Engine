# PIE Fase 3 — auditoria forense do cenário Blender

## Escopo e resultado

Esta auditoria foi somente leitura. Não executei `codex exec`, não iniciei chamadas de modelo, não consumi quota e não alterei código de produção, configurações persistentes ou servidores MCP.

Resultado: `ROOT_CAUSE_UNRESOLVED` para a falha específica do primeiro piloto, mas o defeito de desenho do cenário foi confirmado offline: o prompt ordenava explicitamente o uso de `execute_blender_code` e não havia um contrato de allowlist de ferramentas aplicado pelo cenário.

O primeiro erro de runtime continua sem causa-raiz comprovada porque o JSONL/stderr/resposta MCP daquela sessão não foi preservado.

## Evidência consultada

Checkout auditado:

```text
C:\Users\phsra\OneDrive\Documents\ChatGPT\Korum\Project-Intelligence-Engine
HEAD: 254eda4d6b68255b9b1b3bc9378222c7984c0b1d
```

Arquivos principais:

- `benchmarks/phase3/blender-certification-scenario.json`
- `reports/phase3/54-pilot-manifest-deterministic.json`
- `src/pie/certification/live_codex.py`
- `src/pie/certification/controller.py`
- `src/pie/integrations/blender_mcp_bridge.py`
- `src/pie/integrations/blender_delta.py`
- perfil temporário `pie-phase3-baseline.config.toml`
- perfil temporário `pie-phase3-optimized.config.toml`
- configuração base dos homes temporários do Codex
- `reports/phase3/56-failure-recovery-audit.md`
- testes de bridge e controller

O PIE foi consultado primeiro, mas não é evidência deste checkout: o servidor informou a raiz `C:\Users\phsra\Documents\Codex\2026-11-14\contrato-de-uso-ativo-do-project`, enquanto o checkout auditado está em `C:\Users\phsra\OneDrive\Documents\ChatGPT\Korum\Project-Intelligence-Engine`. O índice remoto retornou `CURRENT` para a outra raiz; portanto, usei inspeção local como fallback e não atribuo seus resultados a este projeto.

## 1. Por que `execute_blender_code` estava disponível

Há três evidências independentes:

1. O prompt do cenário o exige literalmente (`blender-certification-scenario.json:6`): depois de `get_scene_info`, ele ordena chamar `execute_blender_code` uma vez com código Python embutido. Portanto, a ferramenta não foi apenas escolhida espontaneamente pelo modelo; o cenário a prescreveu.
2. A configuração base do home temporário registra o servidor original `blender` com `uvx mcp-for-blender` e não declara uma negação ou filtro de ferramentas para `execute_blender_code` (`config.toml`, seção `[mcp_servers.blender]`). O perfil baseline só define `approval_mode = "approve"` para `get_scene_info` e `get_addon_status`; ele não transforma essa lista em uma allowlist comprovada.
3. O bridge PIE preserva as ferramentas nativas retornadas pelo upstream. `extend_tools` copia a lista recebida e acrescenta `pie_blender_expand` e `pie_blender_scene_delta`; os testes `test_blender_mcp_bridge.py:94-102` verificam que `execute_blender_code` continua em `tools/list`. A documentação também declara que ferramentas desconhecidas passam sem alteração.

A execução histórica confirma a disponibilidade efetiva, independentemente da interpretação estática da configuração: o registro resumido preservado em `reports/phase3/56-failure-recovery-audit.md` mostra `get_addon_status` e `get_scene_info` concluídos, seguidos de `execute_blender_code` com estado `failed`.

Conclusão: a disponibilidade foi esperada pela combinação de prompt explícito + descoberta upstream preservada + ausência de um contrato de allowlist aplicado pelo controlador. O perfil baseline restringia aprovação, mas não provou ocultação da ferramenta.

## 2. O prompt exigia implicitamente a ferramenta?

Não foi implícito: foi explícito.

O texto do cenário contém, na mesma instrução, o nome da ferramenta e o código a executar. A descrição diz “inspect material properties without mutation”, mas a implementação do prompt escolhe a rota de execução arbitrária de Python para obter esses valores.

O hash do prompt está consistente entre cenário e manifesto:

```text
scenario prompt_sha256: ff13ca9d392a3c2ccf5fd74716c166276b4a7f56489d09b58644e0b8edd8d118
manifest prompt_sha256: ff13ca9d392a3c2ccf5fd74716c166276b4a7f56489d09b58644e0b8edd8d118
```

Assim, o manifesto não aponta para uma versão diferente do prompt auditado.

## 3. `execute_blender_code` é necessário para o oráculo?

### Para o cenário atual: sim

O cenário atual obtém `object`, `material`, `roughness` e `metallic` exclusivamente por `bpy` dentro de `execute_blender_code`. Sem essa chamada, o prompt não contém outra instrução que produza os valores usados pelo oráculo.

### Para o requisito semântico do oráculo: não foi demonstrado

O oráculo declara os campos esperados (`object_name`, `material_name`, `roughness`, `metallic`) em `blender-certification-scenario.json:8-13`, mas o contrato local não demonstra que `get_scene_info` ou `get_object_info` retornem todos esses campos com schema estável. Os mocks dos testes comprovam transporte e preservação de ferramentas, não o schema real do addon.

Portanto, não é válido afirmar que `execute_blender_code` é intrinsecamente necessário. A afirmação correta é:

- é necessário para o prompt atual;
- pode ser removido do experimento somente depois de verificar, sem modelo, que uma ferramenta específica de leitura retorna os quatro campos necessários;
- se isso não for possível, deve existir uma ferramenta de consulta read-only com contrato explícito, equivalente nos dois braços;
- não se deve trocar por um oráculo mais fraco apenas para evitar a ferramenta.

## 4. Comparação baseline/optimized

| Aspecto | Baseline | Optimized | Evidência | Avaliação |
|---|---|---|---|---|
| servidor esperado | `blender` | `pie-blender-optimized` | manifesto e `_expected_mcp_server` | equivalente como domínio, diferente como rota |
| upstream | `uvx mcp-for-blender` | gateway PIE → `uvx mcp-for-blender` | perfis temporários | mesmo upstream declarado |
| modelo/esforço | `gpt-5.6-luna` / `medium` | `gpt-5.6-luna` / `medium` | perfis e cenário | equivalente |
| sandbox | `read-only` | `read-only` | perfis | equivalente |
| aprovação | ferramenta específica em `approve` | ferramenta específica em `approve` | perfis | equivalente para as ferramentas declaradas |
| ferramenta `execute_blender_code` no perfil curto | não aparece | não aparece | arquivos de perfil | ausência não prova ocultação |
| descoberta de ferramentas | upstream original | bridge preserva upstream + extensões PIE | bridge e testes | `execute_blender_code` permanece potencialmente visível |
| allowlist de cenário no controller | inexistente | inexistente | `validate_scenario` aceita apenas metadados; não valida ferramentas | lacuna experimental |

Os perfis temporários são TOML válidos. A validação local confirmou que cenário, manifesto e ambos os perfis carregam sem erro e que os hashes de prompt coincidem.

## 5. Relação com o PIE

O bridge não compacta `execute_blender_code`: `OBSERVATION_TOOLS` contém somente `get_scene_info` e `get_object_info`, e a documentação informa que ações como `execute_blender_code` não são compactadas. Isso é coerente com a regra de não aplicar redução lossy a operações de execução.

Há ainda uma dependência interna importante: `pie_blender_scene_delta` constrói uma chamada interna a `execute_blender_code` usando `snapshot_code`. Esse caminho é read-only por construção local e não equivale a permitir código arbitrário do modelo, mas confirma que retirar a ferramenta do upstream sem substituir esse mecanismo quebraria a expansão de contexto do PIE. O cenário auditado, contudo, não chama `pie_blender_scene_delta`.

## 6. O que a evidência histórica prova e não prova

Prova:

- a sessão era Blender baseline;
- `get_addon_status` e `get_scene_info` concluíram;
- `execute_blender_code` foi despachado e falhou;
- a sessão terminou com código externo `1`;
- nenhum par A/B foi aceito.

Não prova:

- o código Python exato que chegou ao addon;
- a mensagem de erro do addon ou do Blender;
- se houve rejeição de sandbox/aprovação;
- se houve erro de estado da cena;
- se a resposta MCP foi malformada;
- tokens do provedor, porque o JSONL da sessão não foi preservado;
- que o prompt determinístico posterior corrigiu o runtime do Codex.

A classificação continua `TOOL_RESULT_FAILURE`, com causa-raiz `INCONCLUSIVE`. O diagnóstico não deve promover o caso a `ROOT_CAUSE_FIXED`.

## 7. Limitações e próximos gates, sem execução paga

Esta auditoria não modificou o cenário nem os perfis. Não executei Codex nem reproduzi a chamada com modelo. Também não encontrei o JSONL/stderr/resposta MCP originais para reconstruir a causa interna da falha.

Antes de qualquer novo A/B, os gates técnicos devem ser:

1. obter o schema real de `get_scene_info`/`get_object_info` por sondagem offline do upstream, sem modelo;
2. decidir entre contrato mínimo de leitura ou execução read-only explicitamente justificada;
3. fazer o manifest/controller validar a allowlist de ferramentas esperadas;
4. manter baseline e optimized com capacidades semânticas equivalentes;
5. preservar stdout, stderr, eventos e respostas sanitizadas por `run_id` antes de iniciar qualquer processo Codex.

## Veredito

`ROOT_CAUSE_UNRESOLVED`

O defeito comprovado é de desenho do experimento: o cenário ordenava `execute_blender_code` e o pipeline não impunha uma allowlist verificável. A necessidade intrínseca dessa ferramenta para o oráculo permanece não comprovada; para o prompt atual, ela é obrigatória. A falha original do runtime continua inconclusiva por perda dos artefatos da sessão.
