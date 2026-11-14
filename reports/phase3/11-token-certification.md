# PIE Fase 3.3 — certificação A/B de tokens

## Veredito

`NOT_CERTIFIED`. A bateria autorizada foi interrompida após a primeira chamada Blender baseline falhar antes de produzir um evento `turn.completed.usage`.

## Execução autorizada

- Modelo: `gpt-5.6-luna`
- Esforço: `medium`
- Planejado: 12 chamadas
- Tentado: 1
- Completo: 0
- Pares válidos: 0
- Chamadas adicionais: nenhuma

## Falha observada

O worktree estava limpo e a configuração isolada foi criada corretamente, mas o `CODEX_HOME` temporário continha `config.toml` sem `auth.json`. O coletor retornou apenas `RuntimeError`, sem uso reportado, e a bateria foi parada conforme a autorização. A configuração original e suas credenciais não foram modificadas nem copiadas para os relatórios.

## Resultados

| Domínio | Baseline | Optimized | Tokens | Oráculo |
|---|---:|---:|---:|---:|
| Blender | falhou antes do turno | não executado | null | não avaliado |
| Web | não executado | não executado | null | não avaliado |

Não há base para calcular economia. Nenhum token foi estimado a partir de caracteres.

## Próximo passo condicionado

Uma nova tentativa exige nova autorização, pois a correção requer disponibilizar autenticação nos `CODEX_HOME` isolados. A alternativa segura é usar autenticação temporária por referência controlada, sem incluir credenciais nos relatórios, e repetir a bateria completa autorizada.
