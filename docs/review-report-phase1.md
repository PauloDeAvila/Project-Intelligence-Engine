# Fase 1 — relatório de implementação e revisão

## Escopo

Esta fase implementa somente o Browser Connector: protocolo de adapter,
gerenciamento de sessões, navegação por origem exata, inventário seguro de
páginas/frames, health check e adapter Playwright opcional. Não implementa
extração de DOM, ranking, quantificação, permissões de ações ou Evidence
Packs.

## Alterações

- `src/pie/web/browser/adapter.py`: protocolo, erros sanitizados, páginas/
  frames e Playwright lazy;
- `src/pie/web/browser/connector.py`: ownership, lifecycle, gerações,
  inventário e reconexão;
- `src/pie/web/browser/navigation.py`: allowlist de origem e validação do
  destino final após redirects;
- `src/pie/web/browser/health.py`: health check sem JavaScript e degradação
  fail-closed;
- `tests/web/test_browser.py`: testes determinísticos sem navegador;
- `tests/web/test_browser_integration.py`: fixture HTTP local e Chromium real;
- `.github/workflows/ci.yml`: job de connector em Ubuntu e Windows, com
  Playwright fixado e Chromium instalado explicitamente;
- `pyproject.toml`: extra opcional `[web]` com `playwright==1.64.1`.

## Segurança e isolamento

- a instalação core não instala Playwright nem inicia browser no import;
- cada lançamento Playwright cria um BrowserContext próprio;
- um adapter não pode ser registrado por duas sessões;
- a navegação solicitada e a origem final após redirect são validadas;
- query strings, fragmentos, credenciais e conteúdo não entram nas
  observações públicas;
- CDP permanece desabilitado até existir contrato de alvo/contexto isolado;
- a API exposta nesta fase não possui evaluate, click, type, submit, upload,
  cookies, headers ou storage;
- health failure degrada a sessão e não reconecta automaticamente.

## Evidência local

Commit da fase: verificar com `git rev-parse HEAD` após o commit.

Comandos executados na branch de implementação:

```text
PYTHONPATH=src python -m unittest discover -s tests/web -v
29 tests OK

PYTHONPATH=src python -m unittest discover -s tests -q
365 tests OK, 2 skipped

python tools/verify_project.py
unit, component, integration, e2e, regression e build passaram

python tools/check_install.py
instalação isolada, importação web e CLI passaram

python -m compileall -q src tools tests
passou

git diff --check
passou
```

O teste de integração iniciou Playwright 1.64.1/Chromium localmente, conectou
uma sessão, enumerou página e frame, navegou em servidor HTTP local e rejeitou
um redirect para outra origem.

Baseline local (Python 3.13.17, Windows, 3 repetições, Chromium headless):

```text
connect p95: 477.5680 ms
navigate p95: 15.6430 ms
health p95:     0.0108 ms
close p95:     45.9762 ms
```

Esses números são baseline de transporte/adapter, não meta de latência
ponta-a-ponta nem prova de aceleração do modelo.

## Revisão independente

O auditor de CI/CD confirmou a Fase 0 e listou os gates necessários para a
Fase 1. A primeira revisão de segurança encontrou três falhas concretas:
registro arbitrário de página, CDP sem isolamento e path sensível exposto.
Esses pontos foram corrigidos, cobertos por testes e verificados novamente
pelos probes locais. A revisão independente final aprovou os cinco invariantes
focalizados: ausência de API pública arbitrária, CDP rejeitado, path redigido,
redirect proibido degradado e import lazy.

## Critério de promoção

A fase só poderá ser promovida após os checks remotos `Web Contracts` e `Web
Connector` em Ubuntu/Windows, a regressão completa, o gate de instalação, a
revisão independente final e a verificação do ruleset remoto. O CI deve falhar
se a instalação do Playwright/Chromium ou o teste HTTP local falhar.
