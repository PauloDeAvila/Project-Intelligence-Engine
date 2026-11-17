# Sonda Codex → PIE → Blender ao vivo

O Blender estava desligado no início da retomada. Após voltar a ficar ativo, o
processo identificado foi Blender 5.3 em `C:\Program Files\Blender Foundation\Blender 5.3\blender.exe`,
com o endpoint MCP `127.0.0.1:9876`.

O Codex `gpt-5.6-luna` chamou `get_addon_status` e `get_scene_info` pelo
servidor `pie-blender-optimized`. O addon respondeu com versão 2.0, protocolo
16/16 e Blender 5.3.0. A cena retornou 3 objetos: 1 mesh, 1 luz e 1 câmera.
Nenhuma alteração foi feita na cena ou na configuração persistente.

Uso reportado: 147.147 tokens de entrada, 123.776 cacheados, 622 de saída e
262 de raciocínio.

Limitação importante: o Codex acionou automaticamente `cua_repl` para o resumo
final, apesar da instrução de usar somente `pie-blender-optimized`. Portanto a
integração ao Blender está comprovada, mas o isolamento estrito de servidores
não passou nesta sessão.
