# PIE Web Intelligence — Fase 1

## Escopo entregue

A Fase 1 adiciona uma fronteira de conexão isolada para navegadores. O
subsisistema principal conhece apenas o protocolo `BrowserAdapter`; Playwright
é opcional e importado somente quando `connect()` é chamado.

Componentes:

- `BrowserConnector`: ownership da sessão, lifecycle e gerações;
- `SessionManager`: registro thread-safe de sessões imutáveis;
- `NavigationController`: navegação GET somente para origens exatas permitidas;
- `BrowserHealthMonitor`: heartbeat sem JavaScript e degradação fail-closed;
- `PlaywrightBrowserAdapter`: implementação opcional para Chromium, Firefox e
  WebKit;
- observações de páginas e frames sem query string, fragmento, credencial ou
  conteúdo de página.

## Limites de segurança

Esta fase não expõe `evaluate`, locators, click, preenchimento, submit,
upload, cookies, headers ou storage. O adapter possui somente conexão,
encerramento, inventário, navegação e health check.

Origens solicitadas e destinos finais após redirect são validados. Um redirect
para origem não permitida degrada a sessão e não gera uma observação pronta
para uso. O mesmo objeto adapter não pode ser registrado em duas sessões.

O lançamento Playwright cria um `BrowserContext` novo por sessão. CDP permanece
desabilitado nesta fase. Um contrato posterior deverá definir alvo, contexto,
ownership e encerramento seguro antes de permitir anexar a um navegador
existente; não há atalho para controlar perfis pessoais.

## Dependência

O núcleo continua instalável sem navegador. Para habilitar o adapter:

```powershell
py -3 -m pip install ".[web]"
py -3 -m playwright install chromium
```

A versão do pacote Playwright está fixada no extra `[web]`. A instalação do
browser é explícita e não ocorre durante importação.

## Verificação

Os testes fake não acessam rede nem iniciam navegador. A integração real usa
servidores HTTP locais e deve ser executada na matriz Ubuntu/Windows antes da
promoção da fase. A promoção exige regressão global, instalação isolada,
`compileall`, checks obrigatórios de CI e revisão independente.

## Fora da fase

Extração de DOM/acessibilidade, indexação, ranking quantitativo, security
policy de ações, Evidence Packs e execução de ações permanecem nas fases
seguintes. Navegação nesta fase é apenas o mecanismo controlado de observação
e transporte.
