# Auditoria de código — consulta seletiva Blender

Data: 2026-11-15  
Base auditada: commit publicado `059483c` + correções deste commit  
Estado: `APPROVED_WITH_RESERVATIONS`  
A/B pago: `PENDENTE`

## Escopo inspecionado

- `tools/simulate_phase3_blender_selective_tasks.py`
- `tools/probe_phase3_blender_query_scene.py`
- `src/pie/gateway/domain.py`
- `src/pie/gateway/mcp_stdio.py`
- `src/pie/integrations/blender_mcp_bridge.py`
- `src/pie/integrations/blender_delta.py`
- `tests/test_blender_mcp_bridge.py`
- `tests/test_blender_delta_stdio.py`
- `fixtures/phase3/blender/large_scene_spec.json`

O PIE foi consultado antes da auditoria: `CURRENT`, `workspace_match=true`, sem diagnósticos. Graphify foi usado para localizar o bridge, a rota de domínio e os chamadores.

## Achados e correções

1. Os oráculos anteriores aceitavam propriedades fracas. Corrigido: A compara nome, tipo, coordenadas `[0.0, 0.0, 0.0]` e material exato; B compara os 10 nomes e a associação de materiais esperada; C compara o conjunto ordenado completo de 64 nomes, tipos, contagens, totais e offsets.
2. O simulador não executava baseline. Corrigido na evidência: o JSON agora declara `experiment_arm=optimized_only` e `ab_comparison=NOT_RUN`; o relatório não chama isso de A/B.
3. A ponte especializada foi auditada. `domain_route(blender)` encaminha para `BlenderMcpBridge`; a consulta PIE é validada antes de gerar um script literal allowlisted, usa uma única chamada interna `execute_blender_code` e devolve o resultado sob contrato próprio.
4. Foram adicionados testes para ausência de duplicação upstream e rejeição de consulta inválida sem dispatch ao Blender.

## Riscos restantes

- O simulador ainda não é uma comparação baseline/optimized e não mede tokens do provedor.
- O script interno é executado pelo addon Blender através de `execute_blender_code`; a segurança efetiva continua dependente do safe mode/permissões do upstream, embora nenhum código arbitrário do argumento seja incorporado.
- A tarefa A/B real precisa usar prompts e oráculos equivalentes, mas as capacidades expostas são diferentes; isso deve ser declarado como experimento de produto.

## Evidência executável

- Simulação real A/B/C do braço optimized: [`81-blender-selective-task-simulation.json`](81-blender-selective-task-simulation.json).
- Probe de contrato/paginação: [`80-real-blender-selective-query.json`](80-real-blender-selective-query.json).
- Suíte: 575 aprovados, 5 ignorados.
- Testes ponte/delta: 15 aprovados.

## Parecer

`APPROVED_WITH_RESERVATIONS` para preparação do piloto. O primeiro par real pode ser planejado para a tarefa A, mas não deve ser tratado como certificação nem como benchmark de compactação transparente. Qualquer falha de rota, uso do provedor, chamada esperada ou oráculo deve interromper o piloto sem retry automático.
