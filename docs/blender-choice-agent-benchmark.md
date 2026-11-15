# PIE Blender — Teste real de escolha entre ferramentas e alvos

O par anterior (340 → 196 tokens, economia de planejamento de **42,353%**,
ambos os oráculos aprovados) validou a integração entre planejamento Qwen,
MCP real e renderização exata. Mas foi um controle simples: só existiam
**uma ferramenta e um alvo**, de forma que o modelo podia sempre devolver
tool_index=0, target_index=0. Os hashes dos planos iguais eram esperados.

Este teste separado elimina essa trivialidade sem tocar nos manifestos de
certificação Codex 106/107.

## Contrato experimental

- Usa **2 ferramentas reais expostas por perfil**, só leitura:
  - Baseline: get_scene_info e execute_blender_code
  - PIE: pie_blender_query_scene e pie_blender_get_object
- A instrução seleciona a ferramenta de consulta exata, não a listagem geral
  da cena nem a pesquisa paginada.
- Em cada tarefa há 3 nomes diferentes, um deles o alvo correto.
- Ordem de ferramentas e índice do alvo mudam entre as tarefas.
  A resposta constante (0,0) não passa no experimento.
- O Qwen3:4B devolve somente dois inteiros: tool_index e target_index.
- O runner valida a seleção *antes* da chamada MCP; nenhuma ação é executada
  se o planejamento errar. Sem retries automáticos.
- Em caso de sucesso, chama um MCP real e renderiza nome/tipo/localização/
  materiais diretamente da observação; nenhum texto do modelo é copiado.
- Um oráculo independente verifica cada objeto com base na fixture
  determinística 8x8 gerada pelo Blender: localização (index % 8, index // 8, 0),
  material PIE_Large_Material_{index // 4:02d}. Divergências falham fechadas.
- Emite consumo de entrada e saída **real do modelo local** apenas na fase
  de planejamento. Não mistura esses tokens com outras arquiteturas.
- Não modifica a cena nem executa Python fornecido pelo modelo.

Este teste ainda é limitado: as ferramentas habilitadas são duas opções
seguras por braço e o prompt solicita explicitamente a consulta exata.
Não prova planejamento amplo do Codex e não mede efeitos de cache/prefetch
ou conversa longa.

## Execução no Windows

Pré-requisitos: worktree experimental, Blender 5.3 com **fixture descartável**
na porta 9877, Ollama local com qwen3:4b. Não use projetos artísticos ativos.

~~~powershell
git fetch origin feat/pie-local-ollama-mcp-benchmark
git merge --ff-only origin/feat/pie-local-ollama-mcp-benchmark

# Uma tarefa: dois braços, uma decisão do modelo por braço
.\tools\run_blender_choice_agent.ps1 -Model qwen3:4b -NumCtx 8192 -MaxTasks 1
~~~

Se ambos os braços tiverem plano e oráculo aprovados:

~~~powershell
# Três tarefas com alvos e posições diferentes, seis decisões ao todo
.\tools\run_blender_choice_agent.ps1 -Model qwen3:4b -NumCtx 8192 -MaxTasks 3
~~~

O relatório JSON novo e imutável fica na pasta TEMP com prefixo
pie-blender-multi-choice-. Ele contém estados, índices selecionados,
hashes e números de tokens, mas não respostas brutas nem valores da cena.

Os resultados podem ser chamados de economia de planejamento local
somente se o oráculo passar nos dois braços da mesma tarefa.
Não compare diretamente com os 42,353% anteriores, pois o universo
de ferramentas e os candidatos mudaram.

## Testes offline

~~~powershell
uv run python -m unittest discover -s tests -p test_blender_choice_agent.py -v
~~~

Não invoca Codex nem APIs pagas. Status Codex: NOT_CERTIFIED.
