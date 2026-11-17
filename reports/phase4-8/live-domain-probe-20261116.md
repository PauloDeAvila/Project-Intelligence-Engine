# Probe dos domínios reais — 16/11/2026

Resultado: `BLOCKED_UPSTREAMS`.

Os dois caminhos de Blender foram chamados sem modificar a cena. O servidor
original e o gateway PIE retornaram falha de handshake com `WinError 10053`,
indicando que a conexão com o Blender foi encerrada pelo processo anfitrião.

O gateway Web também foi chamado contra a fixture local
`http://127.0.0.1:8766`, que retornou `ERR_CONNECTION_REFUSED`. Nenhuma página
externa foi acessada ou modificada.

O relatório não inicia automaticamente Blender, Playwright ou qualquer outro
serviço do usuário. É necessário reativar os upstreams e repetir somente os
probes antes de qualquer benchmark.
