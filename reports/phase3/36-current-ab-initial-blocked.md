# Fase 3 — Sonda A/B inicial no commit atual

## Estado

`BLOCKED` / `NOT_CERTIFIED`.

A preparação offline passou nos quatro preflights com modelo `gpt-5.6-luna`, esforço `medium`, autenticação local validada e commit imutável `d122e7494a6cb43dce1b0ecfb7fcef5920219575`. A fixture Web local foi iniciada durante a sonda e encerrada ao final.

## Evidências

- Gateway Blender direto: `tools/probe_blender_domain_live.py` retornou `PASS` para handshake, `tools/list` e `get_scene_info`; esse probe não mede tokens.
- Primeira captura Codex: `blender-baseline-01` terminou com `NOT_CERTIFIED` / `RuntimeError` e não produziu registro de uso.
- Não foram observados, no worktree temporário, JSONL de captura, eventos de lifecycle ou SQLite para essa tentativa.
- A bateria foi interrompida imediatamente; não foram executados os outros três testes iniciais nem os oito restantes.

## Interpretação

Isto não comprova falha do gateway: o caminho direto do gateway passou. Também não permite afirmar tokens consumidos ou economia, porque não houve registro de `turn.completed` utilizável. A causa precisa ser diagnosticada na camada de execução Codex→MCP/captura antes de qualquer retry pago.

O Blender 5.3 foi localizado em `C:\Program Files\Blender Foundation\Blender 5.3\blender.exe`; não estava no PATH e nenhuma instalação foi feita.

## Certificação

Permanece `NOT_CERTIFIED`. O comparador agora rejeita corretamente qualquer registro sem rota MCP verificada. A autorização da bateria foi consumida apenas como tentativa inicial interrompida; não há base para completar os 12 testes sem corrigir e validar offline a captura Codex.

## Próximo passo seguro

Capturar o erro sanitizado da CLI em uma execução não paga ou ajustar o cenário/perfil para explicitar o servidor disponível, depois repetir somente uma sonda controlada quando a causa estiver comprovadamente corrigida.
