# PIE Fase 3 — roteamento local e medição Web (2026-11-15)

## Escopo

Rodada experimental no worktree `PIE-Local-MCP`, sem iniciar Codex e sem consumir quota. O objetivo foi verificar o roteamento determinístico Blender, o gate MCP Web real e uma medição local de tokens com `qwen3:4b`.

## Evidências executadas

### Blender — roteamento determinístico

Relatório: `C:\Users\phsra\AppData\Local\Temp\pie-blender-multi-choice-d4d40ba968ed.json`

- 3 tarefas, 2 braços por tarefa, 1 chamada MCP por braço.
- Baseline utilizou `execute_blender_code`.
- Optimized utilizou `pie_blender_get_object`.
- Os seis oráculos de fonte passaram; sem omissões ou duplicações.
- Estratégia: `DETERMINISTIC_ROUTING_NO_MODEL`.
- Sessões Codex: 0; tokens Codex: não aplicável.
- Nenhuma economia percentual foi declarada, pois não houve inferência em nenhum braço.

### Web — gate MCP sem modelo

Relatório: `C:\Users\phsra\AppData\Local\Temp\pie-web-ollama-110977214e50.json`

- Fixture local acessível em `127.0.0.1:8766`.
- Baseline e PIE executaram `browser_navigate` e `browser_snapshot`.
- Recuperações: 0.
- Observação: 800 caracteres em ambos os braços.
- Schema visível: baseline 1.332 caracteres; PIE 1.738 caracteres.
- Estado: `MCP_ONLY_NO_MODEL`.

### Web — Qwen local, uma repetição

Relatório: `C:\Users\phsra\AppData\Local\Temp\pie-web-ollama-25dd00d2b564.json`

| Métrica | Baseline | PIE |
|---|---:|---:|
| Entrada | 781 | 887 |
| Saída | 42 | 42 |
| Total | 823 | 929 |
| Latência MCP | 2.738 ms | 3.478 ms |
| Oráculo | PASS | PASS |
| Recuperações | 0 | 0 |

Resultado local: `total_token_savings_percent = -12.88`; `input_token_savings_percent = -13.572`.

Interpretação: nesta fixture, o PIE não reduziu a observação e adicionou schema/contexto. É uma regressão medida, não uma falha de correção. A amostra é de uma repetição e não certifica o produto.

## Validação de código

Comando:

```powershell
uv run python -m unittest tests.test_blender_choice_agent tests.test_blender_choice_stdio tests.test_blender_routing tests.test_local_ollama_benchmark tests.test_pie_domain_gateway tests.test_pie_live_certification -q
```

Resultado: **67 testes aprovados**.

Uma tentativa de `unittest discover` foi interrompida por falta de progresso em testes com dependências externas; não foi contabilizada como aprovação. `pytest` não está instalado neste worktree (`No module named pytest`).

## Estado e limitações

- Roteamento determinístico Blender real: **PASS** nesta execução.
- Web MCP real: **PASS** no gate.
- Web com modelo local: **PASS de correção, regressão de tokens**.
- Agente Qwen multi-choice: permanece `FAILED_CLOSED` na execução anterior; não foi substituído.
- Certificação Codex: **NOT_CERTIFIED**; não houve sessão Codex nem uso de quota.
- A meta de 97% de economia e 99,9% de correção não foi atingida nem inferida.
- O índice PIE MCP disponível nesta sessão aponta para outra raiz; esta rodada usou Graphify do checkout principal e inspeção/execução local como fallback documentado.

## Próxima mudança recomendada

Não promover o Web atual. Investigar o contrato de exposição de `pie_gateway_output_get`: ele foi anunciado mesmo sem ser usado. A próxima alteração deve testar uma política lazy/condicional de recuperação, preservando recuperação para snapshots realmente compactados e removendo overhead quando o snapshot já é completo. Medir novamente com o mesmo prompt, fixture, modelo e `num_ctx=8192`.
