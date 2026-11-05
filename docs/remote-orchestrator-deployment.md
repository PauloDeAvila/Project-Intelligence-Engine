# Implantação remota segura

O gateway local escuta somente em `127.0.0.1`. Não publique sua porta com NAT,
firewall ou uma URL direta. Use o Cloudflare Tunnel como cliente de saída e proteja o
hostname com Cloudflare Access antes de cadastrar o webhook no GitLab.

1. Copie `docs/opencode-orchestrator.example.json` para uma pasta privada e ajuste os
   caminhos absolutos e o allowlist de modelos/projetos.
2. Defina `PIE_ORCHESTRATOR_ADMIN_TOKEN` e `OPENCODE_SERVER_PASSWORD` no ambiente do
   serviço Windows; não os coloque no JSON nem no GitLab.
3. Inicie OpenCode isolado: `opencode serve --pure --hostname 127.0.0.1 --port 4096`.
   A validação local observou o OpenCode 1.19.5 respondendo ao OpenAPI `/doc` com
   autenticação básica em loopback.
4. Inicie o gateway: `pie-orchestrator --config C:\caminho\privado\orchestrator.json`.
5. Crie o túnel, aplique o arquivo-modelo `cloudflared-orchestrator.example.yml` fora
   do repositório e exija Access para o hostname. Mantenha a regra final `404`.
6. No GitLab, envie somente `Issue Hook`, `Merge Request Hook` ou `Pipeline Hook`
   previamente mapeados no JSON local. Inclua `X-Gitlab-Event-UUID`,
   `X-Orchestrator-Timestamp` e `X-Orchestrator-Signature` (HMAC SHA-256 de
   `timestamp + '.' + corpo`); o gateway rejeita UUID repetido, timestamps fora de
   cinco minutos e qualquer evento sem mapeamento.

O túnel não concede permissão de administrador: o endpoint administrativo continua
exigindo o bearer token local. O conteúdo de issue/MR/pipeline é tratado como dado
não confiável e não seleciona projeto, modelo, diretório, comando ou prompt.
