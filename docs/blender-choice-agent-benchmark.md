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


## Falha da primeira execução (preservada)

Na primeira execução real do cenário cube-13-middle, o resultado foi
FAILED_CLOSED com AgentPlanError, sem chamadas MCP nem oráculo. O relatório
original não preservou o subtipo do erro. Um diagnóstico posterior, em
outra inferência, encontrou os índices esperados (1,1), mas não altera
nem valida a tentativa original. Não houve autorização de retry automático.

O runner foi instrumentado **sem modificar prompt, modelo, seed, ordem de
ferramentas ou critério de aprovação**. Em futuras falhas de planejamento,
o relatório passa a incluir campos diagnósticos:

- failed_condition: baseline ou optimized (braço efetivamente interrompido)
- failure_stage: MODEL_PLAN
- failure_code: INVALID_MODEL_JSON, INVALID_PLAN_SHAPE,
  INVALID_TOOL_INDEX, INVALID_TARGET_INDEX, NON_EXACT_TOOL_SELECTED,
  WRONG_TARGET_SELECTED, OLLAMA_TRANSPORT_FAILURE etc.
- mcp_tool_calls_executed: 0 quando a falha ocorreu antes de tools/call
- model_request_attempted: tentativa de requisição ao provedor local
- failed_plan_usage: tokens realmente reportados pelo Ollama *na tentativa
  falha*, quando disponíveis; não entram em economia de par válido
- failed_plan_sha256: impressão digital do texto do modelo, quando disponível
- selected_tool_index / selected_target_index: somente índices inteiros,
  quando validados como presentes, nunca payload bruto

Se a resposta nem chegou a ser recebida, não se inventa token usage nem
hash. Não existe retry/correção automática e a ausência de oráculo continua
registrada. O erro de execução anterior NÃO pode ser reconstituído dos
campos genéricos do relatório já emitido.

Para validar a classificação offline sem consumir Ollama:

~~~powershell
uv run python -m unittest discover -s tests -p test_blender_choice_agent.py -v
~~~

**Não rode novamente o benchmark real sem nova decisão explícita**:
esta atualização publica apenas instrumentação prospectiva, não autoriza
nova execução, não produz nova taxa de economia e não certifica o Codex.


## Caminho funcional automático para consultas exatas (após falha do Qwen)

A tarefa multi-choice com Qwen falhou fechada na primeira execução.
O relatório histórico permanece FAILED_CLOSED, sem oráculo ou economia.
A investigação mostrou que a pergunta já especificava exatamente o
nome de um objeto e o contrato indicava qual operação usar; nesse caso,
submeter a seleção de índices ao Qwen era custo e risco desnecessários.

Foi implementado um roteador reutilizável no código de produção:
src/pie/integrations/blender_routing.py. Ele recebe o catálogo MCP
exposto, os nomes candidatos e o nome solicitado. Somente aceita
correspondência integral, nomes sem duplicatas e ferramentas
estritamente reconhecidas como consultas exatas. Prefere a ferramenta
pie_blender_get_object quando presente; usa execute_blender_code
somente quando essa for a ferramenta de extração disponível e a
execução usar o template de código de leitura auditado. Não gera
Python a partir de texto livre. Falha fechada se faltar informação.

O modo padrão do launcher agora é RouteMode=deterministic. Ele:
- Não chama Ollama e não depende de um modelo instalado
- Seleciona índices diferentes conforme objeto e ordem das ferramentas
- Executa uma chamada MCP real por braço
- Reconstrói quatro campos diretamente da resposta
- Valida o oráculo independente da fixture 8x8
- Registra usage=null e provider_requests=0 em vez de inventar tokens
- NÃO publica uma porcentagem de economia de tokens se ambos os braços
  executaram sem LLM; registra DETERMINISTIC_ROUTING_NO_MODEL

Execução local com fixture descartável Blender 5.3 ativa na porta 9877:

~~~powershell
git fetch origin feat/pie-local-ollama-mcp-benchmark
git merge --ff-only origin/feat/pie-local-ollama-mcp-benchmark

# Todas as três tarefas, no fluxo automático sem modelo
.\tools\run_blender_choice_agent.ps1 -RouteMode deterministic -MaxTasks 3
~~~

A opção RouteMode=model preserva a experiência de seleção por Qwen para
tarefas de pesquisa/avaliação. Nesse modo, os índices são validados antes
de qualquer chamada MCP; erros nunca são promovidos a sucesso e são
registrados com códigos. Nenhum fallback disfarça falhas do modelo:

~~~powershell
# Somente para avaliação do planejador local, não necessário para o roteador
.\tools\run_blender_choice_agent.ps1 -RouteMode model -MaxTasks 3
~~~

No repositório, os testes de roteamento percorrem 64 nomes e rejeitam
catálogos inseguros/malformados. Os testes de integração sobem um proxy
MCP real com upstream Blender *simulado*; não equivalem à execução
gráfica com bpy. A medição de 42,353% de planejamento da experiência
anterior permanece histórica e não se aplica ao roteamento sem LLM.

A certificação Codex continua NOT_CERTIFIED. As fixtures de avaliação
oficial e os manifestos congelados 106/107 não foram alterados.
