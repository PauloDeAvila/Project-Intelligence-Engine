# PIE Fase 3 — auditoria forense offline dos perfis Blender

**Escopo:** comparação independente dos perfis Codex usados no piloto Blender, seus servidores MCP efetivos, comandos, aprovação por ferramenta, workspace, fixture e contrato/oráculo.

**Restrições observadas:** nenhuma execução de `codex exec`, nenhuma chamada paga, nenhuma alteração em `config.toml` persistente, nenhum servidor MCP original modificado e nenhum arquivo de produção alterado. Este relatório é o único artefato criado nesta auditoria.

**Checkout auditado:** `C:\Users\phsra\OneDrive\Documents\ChatGPT\Korum\Project-Intelligence-Engine`

**Branch:** `feat/pie-phase3-task-telemetry-20261114`

**Estado do worktree:** havia somente artefatos não rastreados preexistentes; não foram modificados. O piloto temporário usado pelos perfis foi `C:\Users\phsra\AppData\Local\Temp\pie-phase3-pilot-ddc31cd`.

## 1. Evidência de indexação

O protocolo PIE foi consultado antes da leitura direta. O servidor PIE disponível retornou:

```text
index_state=CURRENT
project=C:\Users\phsra\Documents\Codex\2026-11-14\contrato-de-uso-ativo-do-project
```

Essa raiz não corresponde ao checkout auditado. Portanto, o resultado PIE não foi usado como prova de arquivos, símbolos ou workspace deste projeto. O Graphify local também não pôde ser consultado porque o interpretador salvo em `graphify-out/.graphify_python` estava indisponível e o alias `python` não apontava para um Python instalado. A confirmação foi feita por leitura direta dos artefatos locais, conforme declarado nesta limitação.

## 2. Artefatos e método

Perfis examinados, preservando segredos:

| Perfil | Arquivo | SHA-256 |
|---|---|---|
| baseline | `C:\Users\phsra\AppData\Local\Temp\pie-phase3-pilot-codex-homes-ddc31cd\baseline-home\pie-phase3-baseline.config.toml` | `c4db5928c3a709c750449fd84704a4610effdcfb6a8e8e55778a3b6047ae9e31` |
| optimized | `C:\Users\phsra\AppData\Local\Temp\pie-phase3-pilot-codex-homes-ddc31cd\optimized-home\pie-phase3-optimized.config.toml` | `ef325da1c4f7c12b81e06b2c697514c5aba33fb18e50d6ff7633355110803310` |

Foram usados `tomllib` para parsear TOML, `codex mcp list/get` para confirmar o registro efetivo sem iniciar modelo, e comparação com o manifesto `reports/phase3/54-pilot-manifest-deterministic.json`, o cenário `benchmarks/phase3/blender-certification-scenario.json`, o código do gateway e os testes existentes.

## 3. Perfis efetivos

### Baseline

O `config.toml` do home baseline fornece o servidor original:

```text
server: blender
command: C:\Users\phsra\.local\bin\uvx.exe
args: mcp-for-blender
```

O overlay `pie-phase3-baseline.config.toml` não substitui esse comando; ele contém apenas configurações de modelo, sandbox, ferramentas e aprovação. O servidor Web original `playwright-baseline` também permanece no home baseline, com `@playwright/mcp@0.0.85`.

### Optimized

O overlay registra:

```text
server: pie-blender-optimized
command: <checkout>/.venv/Scripts/python.exe
args: -m pie.gateway.domain serve --domain blender --workspace <pilot-worktree> --max-chars 2400 -- C:\Users\phsra\.local\bin\uvx.exe mcp-for-blender

server: pie-web-optimized
command: <checkout>/.venv/Scripts/python.exe
args: -m pie.gateway.domain serve --domain web --workspace <pilot-worktree> --max-chars 2400 -- C:\Program Files\nodejs\npx.cmd --yes @playwright/mcp@0.0.85 --headless --browser chrome
```

O `codex mcp list` do home optimized confirmou os dois nomes e os comandos acima. O `codex mcp list` do baseline confirmou `blender` e `playwright-baseline`, e não encontrou os nomes optimized.

## 4. Equivalência de capacidades

| Item | Baseline | Optimized | Avaliação |
|---|---|---|---|
| Modelo | `gpt-5.6-luna` | `gpt-5.6-luna` | Equivalente |
| Esforço | `medium` | `medium` | Equivalente |
| Sandbox | `read-only` no overlay, embora o `config.toml` copiado contenha `danger-full-access` | `read-only` no overlay, embora o `config.toml` copiado contenha `danger-full-access` | Depende da precedência do perfil; não comprovado em sessão |
| Upstream Blender | `uvx mcp-for-blender` | o mesmo upstream, atrás do PIE | Equivalente na origem; wrapper adicional no optimized |
| Upstream Web | `@playwright/mcp@0.0.85` direto | o mesmo pacote atrás do PIE | Equivalente na origem |
| Compactação Blender | nenhuma | bridge PIE, que preserva ferramentas e adiciona `pie_blender_expand`/`pie_blender_scene_delta` | Optimized tem capacidade adicional |
| Compactação Web | nenhuma | snapshots Playwright elegíveis podem ser compactados; ações, erros e imagens passam sem redução | Optimized tem transformação adicional condicional |
| Recuperação | não existe | `pie_gateway_output_get` é adicionado pelo gateway stdio | Capacidade adicional; não usada no cenário Blender |
| Servidores não relacionados | `node_repl` e PIE externo continuam no home baseline | `node_repl` e PIE externo continuam no home optimized | Não foram removidos; o cenário exige não usá-los |

Base da comparação: `src/pie/gateway/domain.py:32-49`, `src/pie/gateway/domain.py:112-120`, `src/pie/gateway/mcp_stdio.py:98-129`, `src/pie/integrations/blender_mcp_bridge.py:1-6` e `src/pie/integrations/blender_mcp_bridge.py:27-60`.

**Conclusão de equivalência:** os dois braços não têm capacidade estritamente idêntica na descoberta MCP. O optimized é um superset controlado, como esperado para um gateway, mas a tarefa certificável deve usar somente operações presentes e aprovadas nos dois braços.

## 5. Aprovação por ferramenta

Ambos os overlays declaram:

```text
approval_policy = "never"
sandbox_mode = "read-only"
default_tools_approval_mode = "prompt"
```

Ambos declaram aprovação explícita (`approval_mode = "approve"`) para:

```text
Blender: get_scene_info, get_addon_status
Web: browser_navigate, browser_snapshot
```

O cenário Blender, entretanto, exige também:

```text
execute_blender_code
```

Não há bloco de aprovação específico para `execute_blender_code` em nenhum dos dois perfis. A execução histórica realmente observou `execute_blender_code: failed`, mas não preservou a mensagem de erro. Os registros anteriores confirmam que `approval_policy = "never"` já bloqueou chamadas MCP em outra sonda (`reports/phase3/19-mcp-root-cause.md` e `reports/phase3/20-mcp-remediation-validation.json`); isso é evidência de incompatibilidade da política, não prova de que foi a causa da falha Blender específica.

**Resultado:** aprovação equivalente para as duas chamadas de leitura: **PASS estático**. Aprovação compatível com o cenário completo: **FAIL/INCONCLUSIVO**, porque a terceira ferramenta exigida não está explicitamente coberta e o comportamento não interativo de `never` + `approve` não foi validado nesta auditoria.

O campo global `enabled_tools` contém `get_scene_info`, `get_addon_status`, `browser_navigate` e `browser_snapshot`, mas não contém `execute_blender_code` nem as ferramentas de recuperação PIE. A semântica desse campo para servidores MCP não foi comprovada somente pelo TOML; portanto, não é tratado como uma allowlist por servidor.

## 6. Workspace e isolamento

O manifesto determinístico fixa:

```text
workspace_root = C:\Users\phsra\AppData\Local\Temp\pie-phase3-pilot-ddc31cd
```

O overlay optimized auditado contém o mesmo caminho no argumento `--workspace`. O preflight local já havia retornado `READY_FOR_BENCHMARK` e validado o workspace do gateway. Isso é **PASS estático/preflight**, não prova de que uma futura sessão Codex lançaria apenas essa configuração.

Há uma diferença relevante nos `config.toml` copiados: o home optimized contém rotas com `--workspace` apontando para o checkout principal, enquanto o overlay `pie-phase3-optimized.config.toml` aponta para o worktree temporário. A comparação depende da precedência correta do perfil passado ao Codex. Como não foi permitido executar `codex exec`, essa precedência não foi validada em runtime nesta auditoria.

## 7. Executáveis e dependências

Verificação local, sem iniciar benchmark:

| Dependência | Resultado |
|---|---|
| Python do checkout `.venv/Scripts/python.exe` | Existe |
| `C:\Users\phsra\.local\bin\uvx.exe` | Existe; `uvx 0.13.6` |
| `C:\Program Files\nodejs\node.exe` | Existe; `v26.13.1` |
| `C:\Program Files\nodejs\npx.cmd` | Existe; npm `11.20.0` |
| Codex CLI | Existe; `0.169.0-alpha.11.1` |
| Versão Playwright configurada | Fixada em `@playwright/mcp@0.0.85` |

A disponibilidade do executável não comprova autenticação do provedor nem execução bem-sucedida do upstream.

## 8. Schemas MCP efetivos

### O que foi comprovado

- Os perfis Codex comprovam transportes, comandos e argumentos, mas não carregam os JSON Schemas de `tools/list`.
- O código do gateway preserva as ferramentas upstream e adiciona ferramentas PIE; `tools/list` é transformado em `src/pie/gateway/mcp_stdio.py:196-212`.
- Para Blender, o bridge adiciona `pie_blender_expand` e `pie_blender_scene_delta`, com schemas explícitos em `src/pie/integrations/blender_mcp_bridge.py:27-60`.
- O diagnóstico histórico registrou `tools/list: PASS`, `tool_count: 13` e uma sonda direta de `execute_blender_code` somente leitura aprovada (`reports/phase3/53-blender-execution-diagnosis.json:6-11`).
- Os testes de contrato usam schemas mínimos de mock e verificam que o gateway preserva o schema upstream, por exemplo `tests/test_blender_mcp_bridge.py:94-100` e `tests/test_blender_mcp_bridge.py:125-158`.

### O que não foi comprovado

Não existe no conjunto preservado do piloto um `tools/list` JSON bruto com os schemas completos do upstream Blender para comparar byte a byte baseline versus optimized. Portanto:

- equivalência exata de `inputSchema` dos mesmos nomes upstream: **não verificada**;
- ausência de alteração do schema por `blender_mcp_bridge`: **verificada por contrato/testes**, não por captura do piloto;
- presença e schema de `execute_blender_code` no servidor efetivo Codex: **não verificada no registro**, embora tenha sido emitida como chamada na sessão falha;
- aceitação do código de leitura pelo runtime Codex: **não verificada**.

## 9. Fixture e oráculo

O cenário `benchmarks/phase3/blender-certification-scenario.json` define:

```text
scenario_id: blender-material-cert-v1
model: gpt-5.6-luna
required_mcp_server: blender
expected_exact: PIE_BLENDER_CERT_ORACLE_V1
object: PIE_AB_Cube
material: PIE_AB_Material
roughness: 0.35
metallic: 0.2
```

A fixture local necessária existe. O hash observado para `fixtures/phase3/web/index.html` foi `d48ce3c3fe568c957045d78871119b6aa6130e86dd12866f15109a6a84008300`; ela é Web e não substitui a validação independente do Blender.

O oráculo do controlador verifica apenas a presença dos nomes do objeto/material e marca que o probe Blender independente é obrigatório (`src/pie/certification/controller.py:186-197`). A evidência histórica independente `reports/phase3/41-blender-material-oracle.json` observou `PIE_AB_Cube`, `PIE_AB_Material`, roughness aproximadamente `0.35` e metallic aproximadamente `0.20`, sem mutação. Isso é evidência de fixture/oráculo preparado, não resultado válido do piloto falho.

**Risco metodológico:** a resposta textual fixa `PIE_BLENDER_CERT_ORACLE_V1` prova somente que o agente respondeu com o marcador esperado. Ela não prova que as ferramentas produziram os valores corretos. A correção depende do probe independente e de chamadas MCP bem-sucedidas.

## 10. Relação com a falha histórica

A execução preservada foi:

```text
baseline / Blender / repetition 1
run_id = baseline-409e2a71803509b546248d24
pair_id = pair-d4b179952cf4570b9d7d97f7
```

Linha do tempo preservada:

```text
get_addon_status       completed
get_scene_info         completed
execute_blender_code   failed  <-- primeira falha observada
executor               failed
```

O relatório forense `reports/phase3/56-failure-recovery-audit.json` confirma que JSONL bruto, stderr, resposta MCP, lifecycle, SQLite, oráculo e usage não foram preservados para esse `run_id`. O diagnóstico offline posterior confirma handshake, `tools/list` e probe de execução somente leitura, mas não reproduz o comportamento do modelo (`reports/phase3/53-blender-execution-diagnosis.json`).

Assim, a auditoria não atribui a falha a Blender, PIE, sandbox, approval ou código gerado sem o evento textual correspondente.

## 11. Resultado por requisito

| Requisito | Resultado | Evidência |
|---|---|---|
| Perfis parseáveis | PASS | `tomllib` nos dois overlays |
| Servidor baseline original identificado | PASS | `codex mcp list/get` no home baseline |
| Gateway optimized identificado | PASS | `codex mcp list/get` no home optimized |
| Mesmo upstream Blender | PASS | `uvx mcp-for-blender` nos dois braços |
| Mesmo modelo/esforço | PASS estático | overlays e cenário |
| Workspace optimized igual ao manifesto | PASS no overlay/preflight | `--workspace` no perfil optimized |
| Aprovação das leituras usadas | PASS estático | blocos `approval_mode = "approve"` |
| Aprovação de `execute_blender_code` | FAIL/INCONCLUSIVO | ausente no perfil; política global `never` |
| Schemas completos baseline/optimized | NÃO VERIFICADO | nenhuma captura `tools/list` bruta preservada |
| Fixture Blender | PASS preparado | oráculo histórico independente |
| Oráculo independente aplicado ao piloto | NÃO | piloto falhou antes da avaliação |
| Segredos expostos | PASS | somente caminhos, hashes e estados sanitizados registrados |
| `codex exec`/quota nesta auditoria | PASS | não executado |

## 12. Veredito

`BLOCKED_WITH_SPECIFIC_CAUSE`

O bloqueio específico é metodológico/configuracional: o cenário Blender pede `execute_blender_code`, mas o contrato de aprovação está explicitamente documentado apenas para duas operações de leitura, enquanto `approval_policy = "never"` já foi demonstrado incompatível com chamadas MCP que exigem aprovação. A ausência dos JSON Schemas brutos e das respostas/erros da sessão histórica impede uma certificação mais forte.

Este relatório **não** conclui que `execute_blender_code` é intrinsicamente necessário, seguro ou a causa raiz da falha histórica. Para um novo benchmark, fora do escopo desta auditoria, seria necessário primeiro escolher uma tarefa que use apenas uma allowlist explicitamente equivalente nos dois braços ou adicionar aprovação controlada e validar os schemas reais; depois capturar `tools/list`, eventos e respostas em arquivos por `run_id` antes do dispatch.

## 13. Arquivos consultados

- `benchmarks/phase3/blender-certification-scenario.json`
- `reports/phase3/53-blender-execution-diagnosis.json`
- `reports/phase3/56-failure-recovery-audit.json`
- `reports/phase3/41-blender-material-oracle.json`
- `reports/phase3/54-pilot-manifest-deterministic.json`
- `src/pie/gateway/domain.py`
- `src/pie/gateway/mcp_stdio.py`
- `src/pie/integrations/blender_mcp_bridge.py`
- `src/pie/certification/live_codex.py`
- `tools/prepare_phase3_profiles.ps1`
- `tests/test_blender_mcp_bridge.py`
- `tests/test_pie_certification_controller.py`

