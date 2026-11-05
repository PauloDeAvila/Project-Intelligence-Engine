# PONTO.md — revisão separada do estágio GitLab outbound (PR #39)

**Escopo:** adição incremental à branch `exp/opencode-remote-orchestrator`;
nenhuma alteração na `main`. Este relatório é revisão interna de código,
**não aprovação independente de outro agente**.

## Caminho implementado
- `pie-orchestrator-gitlab-poll` consulta `gitlab.com/api/v4/projects/{numeric_id}/issues`
  com rótulo fixo e token local, sem expor porta HTTP no Windows.
- Exige allowlists de ID numérico de autor, projeto local, tipo de tarefa,
  modelo e rótulo; ignora título, corpo e comandos de issues.
- Usa SQLite `TaskStore` para idempotência entre scans/reinícios.
- **Por padrão só enfileira**. A flag local `--execute` dispara
  `Orchestrator.run` para tarefas PENDING; não vem da issue.
- Em resultado terminal, tenta publicar somente ID, status e contadores
  de tokens retornados pelo provedor, sem incluir prompts ou resultados brutos.
- Interrompe quando a resposta GitLab exige paginação para não fingir
  lista ou verificação de notas completa.

## Impacto
- Novo módulo: `src/pie/orchestrator/gitlab_poll.py`
- Nova entrada CLI em `pyproject.toml`
- Novos testes isolados `tests/test_gitlab_poll.py` (6 testes escritos)
- Docs de instalação e exemplo JSON para o objeto `gitlab_poll`.
- Não altera indexador PIE, grafo, MCP, gateway HTTP existente nem modelos
  permitidos nos projetos.

## Evidência/limites
- GitHub connector publicou os commits na branch. **Não houve nova
  execução de GitHub Actions visível para esses commits**; não afirmar
  testes aprovados, Pyright aprovado ou Windows validado.
- 6 testes unitários foram adicionados, mas **ainda não foram executados
  neste ambiente**.
- Nenhuma chave GitLab, conta Cloudflare, instância OpenCode nem computador
  Windows foi acessada, portanto o fluxo remoto fim a fim NÃO ESTÁ
  COMPROVADO.
- O adaptador OpenCode legado do PR #39 ainda não implementa uma política
  verificável de negação de bash/edição/web. O prompt read-only não basta
  para impor essas restrições.
- A consulta a issues não constitui evento push em tempo real; depende
  de polling. A entrega de nota não é transacional/exatamente-uma-vez
  em caso de múltiplos workers ou falha após POST.
- A versão inicial não devolve a resposta textual do agente ao GitLab
  por padrão, apenas estado e contadores.

## Gate
**NOT VERIFIED / NOT APPROVED** para ativação automática remota ou merge.
Requer, em sequência: suite completa Linux/Windows, Pyright,
teste local sem `--execute`, revisão de permissões do OpenCode,
uma execução real autorizada pelo usuário com `--execute`,
e teste real de nota no GitLab com token restrito.
