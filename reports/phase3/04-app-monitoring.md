# Fase 3 — monitoramento por aplicativo

## Blender

O proxy cobre ferramentas de cena/material configuradas para compactação e mantém recuperação sanitizada por `output_id`. Mede caracteres fonte/devolvidos, estado, ferramenta e duração. A correção de alterações reais exige Blender e oráculo `bpy`; Blender não está instalado nesta máquina, portanto não houve benchmark.

## Web / Playwright

O perfil `web` usa `web_result_eligible` e `web_snapshot_preview`, preservando referências e URLs relevantes quando presentes. O proxy não executa navegação adicional; recuperação é local e paginada. Não houve página local Playwright executada neste ambiente.

## Persistência e operação

- SQLite local com WAL, `busy_timeout=5000`, índices por tarefa/execução/data.
- Retenção: ledger de tarefa até 100.000 linhas; métricas legadas até 1.000 linhas.
- Monitoramento é instrumentação local e best-effort; uma falha de persistência não interrompe uma chamada MCP funcional.
- Exportação JSON via `pie-usage report --output`; filtros por app, task, run e intervalo ISO UTC.
- Chamadas sem resposta JSON final ainda não recebem evento de timeout; isso permanece limitação conhecida.

