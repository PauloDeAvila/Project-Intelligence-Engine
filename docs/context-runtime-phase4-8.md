# Context Runtime — execução das Fases 4–8

Este documento transforma o roadmap de consolidação em gates executáveis. Os
estados abaixo distinguem contratos locais comprovados de integrações externas
que ainda precisam de um ambiente real.

## Fase 4 — Consolidação

Verificar a raiz do índice, a sequência linear da branch, o diff acumulado, a
suíte completa, os contratos MCP e a persistência após reinício.

Comandos:

    uv run python -m pie.interfaces.cli index --root .
    uv run python -m pie.interfaces.cli status --root .
    uv run --with pytest python -m pytest -q --basetemp .pytest-tmp-phase4-full

Aceite local: index_state=CURRENT, workspace_match=true, suíte sem falhas e
MCP sem regressão. A raiz do servidor MCP ativo deve ser conferida
separadamente; status de outra raiz não é evidência deste checkout.

## Fase 5 — Memória entre agentes

O agente de origem salva um checkpoint limitado e hash-verificado. Cada
checkpoint expõe `context_version`, uma versão durável derivada da sequência
SQLite e vinculada ao agente pela proveniência. O handoff explícito cria um
checkpoint para o agente receptor, com proveniência da origem. O receptor
restaura somente esse checkpoint, sem receber o histórico completo.

O contrato é coberto por test_multi_agent_memory_handoff_survives_agent_boundary
e pela integração da facade em test_context_runtime.py. Um handoff controlado
OpenCode/DeepSeek também foi executado; ele não representa certificação geral
de qualidade ou economia.

## Fase 6 — Contexto incremental e cache

Usar ContextCompiler, hashes de origem, deltas persistentes e recuperação
fail-closed. O cache de evidências é persistente e é revalidado após reinício;
qualquer mudança no manifesto SHA-256 invalida a entrada. Um orçamento só pode
ser aplicado com contador de tokens real fornecido pelo chamador; caracteres
não são convertidos em tokens.

Aceite externo exige usage do provedor após reinício do agente. O contador
sintético do verificador é apenas um gate de contrato e não certifica tokens.

## Fase 7 — Execução local inteligente

Somente OperationSpec registrada pode executar. Argumentos/resultados são
limitados, dados sensíveis são rejeitados, replay é idempotente e timeout
rígido falha fechado quando não pode ser aplicado.

Aceite local: testes de allowlist, replay, timeout cooperativo e timeout
rígido. Integrações Blender/Web continuam sujeitas aos seus oráculos e
permissões específicos.

## Fase 8 — Certificação contínua

ContinuousCertification exige uso real do provedor, identidade pareada, rota
MCP verificada, oráculo aprovado, latência e chamadas MCP. Ausência de
qualquer campo mantém NOT_CERTIFIED.

O piloto GLM v5 existente é evidência complementar: três tarefas corretas em
cada braço e 88,875% de economia total, mas não substitui a bateria Codex
pareada Blender/Web nem uma amostra estatística mais ampla.

## Resultado desta rodada

O handoff da Fase 5 foi implementado e testado. As fases 4 e 7 estão
validadas localmente. As fases 6 e 8 permanecem parciais até haver integração
real do agente e evidência de provedor/rota na raiz correta.
