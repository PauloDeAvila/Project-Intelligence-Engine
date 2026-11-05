# PIE Web Intelligence — Fase 2

## Escopo

A Fase 2 transforma uma árvore de acessibilidade ou metadados DOM em um
`PageSnapshot` compacto e vinculado à sessão. Nenhum LLM é usado para extrair
ou localizar elementos.

Componentes:

- `AccessibilityNode` e `ElementRecord`: entradas inertes e limitadas;
- `AccessibilityExtractor`: flattening determinístico com limite de profundidade
  e quantidade;
- `PlaywrightDOMExtractor`: leitura somente de locators fixos, sem selector
  fornecido pelo modelo, sem `evaluate` e sem ações;
- `SnapshotNormalizer`: hashes, refs snapshot-bound, roles/actions declarativas
  e `UNTRUSTED_PAGE_DATA`;
- `ElementRegistry`: busca literal por role/nome, sem CSS/XPath;
- `PageStateTracker`: current/partial/stale conforme geração e hash.

## Segurança

Roles desconhecidos não desaparecem: viram elementos `UNSUPPORTED` sem ações.
Campos de página continuam não confiáveis e são redigidos pela serialização
dos contratos. Snapshots excedentes tornam-se `PARTIAL` e registram
`omitted_count`; o limite padrão é 512 elementos.

A extração Playwright só é acessível através de uma sessão `BrowserConnector`
READY: o inventário verifica página, frame principal e origem autorizada antes
de ler metadados. IDs de página não dependem da posição no inventário. O
registry e o tracker também têm capacidades máximas para evitar crescimento
ilimitado em processos longos.

A lista de ações é uma capacidade declarativa fechada por role e estado
`enabled`; dados da página não podem fabricar uma operação incompatível.

Paths continuam sem query ou fragmento. A normalização não interpreta nome,
role ou texto como código, selector, script ou autorização.

## Dependências e CI

O núcleo continua sem browser. O job `Web Page Intelligence` instala o extra
Playwright fixado, instala Chromium explicitamente e executa testes determinís-
ticos e integração com servidor HTTP local em Ubuntu e Windows. O job de
contratos continua separado e não precisa iniciar navegador.

## Fora da fase

Ranking de relevância, busca FTS/semântica, redução quantitativa, security
policy de ações, Evidence Packs e execução permanecem nas fases seguintes.
