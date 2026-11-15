# PIE Fase 3 — correção forense do benchmark Blender

## Veredito

`ROOT_CAUSE_UNRESOLVED` / `NOT_CERTIFIED`

Esta etapa foi exclusivamente offline. Não houve nova sessão `codex exec`, consumo de quota, alteração de `config.toml`, alteração dos servidores MCP originais ou benchmark A/B.

## Alterações

- `src/pie/certification/live_codex.py` agora cria evidências por `run_id` antes do processo Codex.
- Falhas de preflight, timeout, exit code, JSONL inválido, ausência/ambiguidade de usage e rota MCP inválida preservam artefatos parciais e não fazem retry automático.
- Eventos, stderr, nomes/status de ferramentas e usage numérico são sanitizados; prompts, respostas completas, argumentos e credenciais não são persistidos.
- `tests/test_pie_forensic_capture.py` cobre as falhas exigidas e a interrupção após a primeira falha.
- `agent-scenario-audit.md` e `agent-profile-audit.md` registram a auditoria independente.

Por execução, o diretório forense contém `manifest.json`, `codex-events.jsonl`, `codex-stderr.log`, `mcp-tool-events.jsonl`, `provider-usage.json`, `oracle-result.json` e `run-result.json` (além do log sanitizado de stdout).

## Causa técnica ainda não resolvida

O cenário Blender prescreve `execute_blender_code`, mas a aprovação preparada cobre apenas `get_scene_info` e `get_addon_status`; não existe uma allowlist efetivamente aplicada pelo cenário. A sessão histórica não preservou JSONL, stderr ou resposta MCP suficientes para provar se a falha foi aprovação, sandbox, addon, código gerado ou resposta inválida. A auditoria, portanto, não promove o caso a `ROOT_CAUSE_FIXED`.

Antes de qualquer A/B, é necessário escolher uma allowlist semanticamente equivalente nos dois braços, capturar os schemas reais de `tools/list` e executar uma única sonda controlada somente após o gate de aprovação.

## Validação reproduzível

```text
uv run python -m unittest tests.test_pie_forensic_capture -v
  10 passed

uv run python -m unittest discover -s tests -q
  561 tests, OK; 5 skipped

uv run python -m compileall -q src tests
  PASS

git diff --check
  PASS

uv run python -m pie status --root .
  CURRENT; workspace_match=true; diagnostics=[]

graphify query "forensic capture live Codex run_id MCP events" --budget 700 --depth 2
  PASS; graph local com 3394 nós
```

Observação: o executável `pytest` não está instalado no `.venv`; por isso a suíte foi executada pelo `unittest` suportado pelo projeto. O resultado dos testes não é evidência de tokens do provedor.

## Próximos gates

1. Corrigir a allowlist/aprovação do cenário Blender sem abrir operações arbitrárias.
2. Confirmar schemas e capacidade read-only do upstream sem modelo.
3. Executar uma sonda real isolada e verificar os artefatos por `run_id`.
4. Somente após sucesso, retomar os pares A/B autorizados e manter a certificação baseada em usage real.
