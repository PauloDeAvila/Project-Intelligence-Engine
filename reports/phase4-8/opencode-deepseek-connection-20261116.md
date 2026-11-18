# Conexão OpenCode → Infinity → DeepSeek 3.2

## Resultado

`PASS`: o endpoint local anunciou `gambiarraapi/deepseek-v3.2` e o OpenCode
executou uma chamada real usando `infinity/deepseek-v3.2`.

- Endpoint: `http://127.0.0.1:8080/v1`
- Configuração: `C:/Users/phsra/Downloads/Infinite/opencode.json`
- Resposta do probe: `DEEPSEEK_OK`
- Entrada reportada: 55 tokens
- Saída reportada: 6 tokens
- Cache de entrada reportado: 6.394 tokens
- Reasoning reportado: 0 tokens
- Custo reportado: 0

O GLM permanece cadastrado para fallback/rollback, mas não é o modelo padrão.
Nenhuma chave ou credencial foi registrada neste artefato.

## Limitação

Esta prova valida o provider no OpenCode/Infinity. Ela não substitui a
certificação Codex nem prova economia de tokens em uma tarefa Blender/Web.
