# PIE Fase 3 — compatibilidade MCP de `structuredContent`

Data: 2026-11-15  
Estado: `OFFLINE_VALIDATED`  
Certificação: `NOT_CERTIFIED`

## Decisão

O gateway Blender agora inspeciona o `outputSchema` recebido em `tools/list` antes de transformar uma observação.

- Sem `outputSchema`: pode compactar somente `result.content[0].text` quando a resposta é textual, grande, bem-formada e explicitamente elegível. `result.structuredContent` é preservado sem alteração.
- Com `outputSchema`: a resposta inteira permanece `PASSTHROUGH`; o contrato tipado é tratado como autoridade.
- Texto JSON acompanhado de `structuredContent`, erros, conteúdo misto e conteúdo não textual permanecem `PASSTHROUGH`.
- A recuperação continua apontando para o original sanitizado; nenhum token é inferido a partir de caracteres.

Isso resolve o bloqueio funcional sem converter a estrutura tipada em texto nem truncar campos desconhecidos. A semântica do cliente ainda precisa ser confirmada em uma execução real do Codex antes de qualquer certificação.

## Evidências

| Verificação | Resultado |
|---|---|
| Testes Blender bridge + gateway | 28 aprovados |
| Suíte completa | 573 aprovados, 5 ignorados |
| `git diff --check` | PASS |
| Sessões de modelo nesta etapa | 0 |
| Quota consumida nesta etapa | não |
| Web alterado | não |
| A/B Blender executado | não |

Testes específicos cobrem retorno estruturado sem schema, retorno com schema declarado e texto JSON estruturado. O probe real anterior continua válido como evidência de que a resposta Blender contém `structuredContent`; este commit não o reclassifica retroativamente como economia de tokens.

## Limitações e próximo gate

O `outputSchema` ausente não prova que todos os clientes ignoram `content` quando `structuredContent` existe; por isso a compactação é limitada à apresentação textual e continua sem certificação de equivalência do agente. Antes de A/B Blender, repetir o probe MCP offline com o checkout atualizado e confirmar `COMPACTED` no retorno real, preservação de `structuredContent` e recuperação exata. Depois disso, executar apenas o piloto controlado autorizado, mantendo `NOT_CERTIFIED` até haver tokens reais pareados.

PIE consultado antes da alteração: estado `CURRENT`, `workspace_match=true`, raiz `C:\Users\phsra\OneDrive\Documents\ChatGPT\Korum\Project-Intelligence-Engine`. Graphify foi usado para localizar o bridge, a política de compactação e os chamadores.
