# PIE — medição local MCP + Ollama, sem quota Codex

Este experimento é independente dos manifestos congelados 106/107.
Ele invoca os MCPs baseline e optimized reais, captura schemas e respostas,
e envia esse material para um modelo Ollama rodando localmente.
Compara tokens reais reportados pelo Ollama (prompt_eval_count, eval_count),
latência, chamadas MCP e acerto dos oráculos.

**Importante:** a ferramenta executa as chamadas MCP de forma determinística.
A IA local só analisa as observações. Isso NÃO certifica o agente Codex nem
substitui os cinco pares GPT-5.6 pendentes.

## Requisitos

- Python 3.12+, Ollama local em 127.0.0.1:11434, modelo qwen3:4b
- Blender com fixture descartável e MCP ativo na porta 9877
- Para Web, Node/npx, Chrome/Playwright e fixture servida na porta 8766

~~~powershell
ollama pull qwen3:4b
ollama list
~~~

## Blender: geração de perfis

No checkout experimental do PIE:

~~~powershell
$repo = (Get-Location).Path
$profiles = Join-Path $env:TEMP 'pie-local-blender-profiles'
.\tools\prepare_phase3_profiles.ps1 -Workspace $repo -OutputDirectory $profiles -Domain blender -BaselineExposeTool execute_blender_code -OptimizedExposeTool pie_blender_query_scene -BlenderPort 9877
~~~

Não use sua cena artística: somente a instância descartável do Blender 5.3
com a fixture de 64 objetos e 16 materiais.

Primeiro teste as ferramentas, sem chamar nenhum modelo:

~~~powershell
python .\tools\benchmark_local_ollama.py --workspace $repo --scenario .\benchmarks\phase3\blender-selective-task-a-v3-scenario.json --baseline-profile (Join-Path $profiles 'pie-phase3-baseline.config.toml') --optimized-profile (Join-Path $profiles 'pie-phase3-optimized.config.toml') --probe-only --output (Join-Path $env:TEMP 'pie-blender-mcp-only.json')
~~~

Depois execute o A/B com tokens realmente contabilizados pelo modelo local:

~~~powershell
python .\tools\benchmark_local_ollama.py --workspace $repo --scenario .\benchmarks\phase3\blender-selective-task-a-v3-scenario.json --baseline-profile (Join-Path $profiles 'pie-phase3-baseline.config.toml') --optimized-profile (Join-Path $profiles 'pie-phase3-optimized.config.toml') --model qwen3:4b --repetitions 3 --num-ctx 16384 --output (Join-Path $env:TEMP 'pie-blender-ollama-ab.json')
~~~

## Web: fixture HTTP e perfis

Em outro terminal:

~~~powershell
python -m http.server 8766 --bind 127.0.0.1 --directory .\fixtures\phase3\web
~~~

No terminal do checkout:

~~~powershell
$webProfiles = Join-Path $env:TEMP 'pie-local-web-profiles'
.\tools\prepare_phase3_profiles.ps1 -Workspace $repo -OutputDirectory $webProfiles -Domain web -BaselineExposeTool browser_navigate,browser_snapshot -OptimizedExposeTool browser_navigate,browser_snapshot,pie_gateway_output_get
python .\tools\benchmark_local_ollama.py --workspace $repo --scenario .\benchmarks\phase3\web-local-page-v2-scenario.json --baseline-profile (Join-Path $webProfiles 'pie-phase3-baseline.config.toml') --optimized-profile (Join-Path $webProfiles 'pie-phase3-optimized.config.toml') --model qwen3:4b --repetitions 3 --num-ctx 16384 --output (Join-Path $env:TEMP 'pie-web-ollama-ab.json')
~~~

## Validação e limites

- Um erro em initialize, tools/list, tools/call ou nos fatos da fixture
  interrompe o benchmark antes de enviar a observação ao modelo local.
- O oráculo precisa aprovar os dois braços para registrar uma comparação.
- Cada arquivo de saída é write-once; não sobrescreve relatórios anteriores.
- Os relatórios registram hashes, metadados e números, não prompts/respostas.
- As diferenças de tokens aqui refletem o **modelo local** e o replay
  das observações; não representam a cobrança nem a configuração do Codex.

Para testar somente a lógica de benchmark:

~~~powershell
python -m unittest discover -s tests -p test_local_ollama_benchmark.py -v
~~~

O branch experimental não modifica os cenários, fixtures, manifesto 106,
plano 107 nem a certificação NOT_CERTIFIED.


## Atalho PowerShell (recomendado)

Depois de ligar o Blender MCP com a fixture ou o servidor HTTP Web,
um único comando configura perfis separados e executa o runner:

~~~powershell
.\tools\run_phase3_local.ps1 -Domain blender -ProbeOnly
.\tools\run_phase3_local.ps1 -Domain blender -Model qwen3:4b -Repetitions 3
.\tools\run_phase3_local.ps1 -Domain web -Model qwen3:4b -Repetitions 3
~~~

Cada execução cria um arquivo JSON único no diretório temporário. O primeiro
comando não chama nenhum modelo. Os dois seguintes usam exclusivamente
o Ollama local. A disponibilidade do Blender, Web e Ollama reais precisa
ser verificada no computador do usuário antes de interpretar os números.


## Auditoria de fidelidade ao Codex (após primeiro replay Ollama)

O primeiro ensaio Blender local, realizado com Qwen3:4B e num_ctx=8192,
registrou 84,712% de economia total em três repetições. **Esse ensaio usou o
catálogo integral de ferramentas anunciado pelo servidor**: 10 ferramentas
baseline vs 1 PIE. No perfil Codex do cenário Blender, porém, enabled_tools
restringe o baseline a execute_blender_code e o optimized a
pie_blender_query_scene. O contexto realmente exibido pelo Codex pode ser
diferente do catálogo MCP bruto.

Para quantificar esse efeito sem modificar nem sobrescrever os resultados
anteriores, o launcher agora expõe dois modos independentes:

~~~powershell
# Prioridade: somente schemas habilitados nos perfis, mais próximo da configuração Codex
.\tools\run_phase3_local.ps1 -Domain blender -Model qwen3:4b -NumCtx 8192 -Repetitions 3 -SchemaScope profile

# Reprodução da metodologia anterior: todo tools/list bruto (10 vs 1)
.\tools\run_phase3_local.ps1 -Domain blender -Model qwen3:4b -NumCtx 8192 -Repetitions 3 -SchemaScope server
~~~

O campo schema_scope é gravado no relatório e cada arquivo tem nome único.
O modo profile é padrão. O número de ferramentas realmente anunciadas pelo
servidor permanece em server_tool_count, enquanto tool_count registra as
ferramentas visíveis no contexto preparado pelo runner.

Essa mudança **não é uma medição do contexto interno do Codex**. Serve para
identificar o quanto a economia de 84,712% dependia da inclusão de ferramentas
que já estariam desabilitadas no perfil cliente. As contagens reais do Codex
continuam dependendo do protocolo pago 106/107.

O contexto padrão do launcher foi reduzido para 8192, pois 16384 causou erro
CUDA no hardware de referência. Se o runtime/modelo não suportar esse tamanho,
reduza o contexto apenas após confirmar que o prompt não foi truncado.


## Web: resolução automática do npx.cmd

O launcher verifica primeiro o PATH, depois locais comuns de instalação do
Node.js no Windows. Se Node estiver instalado fora desses caminhos:

~~~powershell
.\tools\run_phase3_local.ps1 -Domain web -ProbeOnly -NpxExe 'C:\Program Files\nodejs\npx.cmd'
~~~

Se o Node/npx não estiver realmente instalado:

~~~powershell
winget install -e --id OpenJS.NodeJS.LTS
~~~

Abra um terminal novo e rode o Web -ProbeOnly. Não há instalação
automática de Node pelo runner; ele falha com diagnóstico acionável.
