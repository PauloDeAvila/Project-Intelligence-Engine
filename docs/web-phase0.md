# PIE Web Intelligence — Fase 0

## Escopo

A Fase 0 estabelece contratos tipados e observabilidade para o subsistema web
sem iniciar navegador, acessar rede, executar JavaScript ou adicionar
dependências de runtime. O núcleo de indexação de Python permanece isolado.

## Contratos

Schema: `pie-web-contracts-v1`. Todos os contratos são imutáveis, possuem
serialização JSON determinística. Cookies, headers, tokens, valores de campos
e texto livre de página/intenção não são exportados em bruto.

- `BrowserSession`: estado da sessão, geração, capacidades e allowlist exata de origens.
- `PageSnapshot`: observação imutável e delimitada de uma página.
- `ElementReference`: referência vinculada a página, snapshot e geração.
- `ElementCandidate`: elemento normalizado, único no snapshot e marcado como dado de página não confiável.
- `TaskIntent`: ação/transição declarativas; `goal` e `target_query` são texto literal não executável.
- `ActionResult`: envelope de resultado; sucesso exige execução concluída e verificação positiva.
- `WebMetric`: latência, tokens e erro operacional sem conteúdo de página.

## Invariantes

1. Importar `pie.web` não inicia navegador nem faz rede.
2. Origens autorizadas são exatas; curingas e credenciais não são aceitos.
3. Referências carregam `page_id`, `snapshot_id` e `generation`.
4. Referências obsoletas são explícitas e nunca são tratadas como atuais.
5. Sessão fechada não pode voltar a um estado ativo.
6. Falhas de ação exigem código de erro.
7. Métricas não carregam conteúdo da página, cookies ou credenciais.
8. Snapshots têm estado explícito (`CURRENT`, `PARTIAL`, `STALE` ou `BLOCKED`).
9. Origens curinga, URLs com credenciais e esquemas não HTTP(S) são rejeitados.
10. Dados derivados da página permanecem `UNTRUSTED_PAGE_DATA`.
11. Roles, sources, actions, métricas e timestamps usam vocabulários/formatos fechados.
12. Serialização redige texto livre de página/intenção e não aceita `NaN`, infinitos ou surrogates Unicode isolados.

## Verificação

O tier dedicado roda com:

```powershell
py -3 -m unittest discover -s tests/web -v
```

O job CI dedicado executa esse tier em Ubuntu e Windows, sem navegador, rede
ou credenciais.

Os laboratórios que usam segredos de API não fazem parte do gatilho de
pull-request; devem ser executados manualmente por `workflow_dispatch`.

A suíte global e os gates existentes continuam obrigatórios antes de qualquer
promoção. O relatório independente deve registrar o commit, a matriz completa
e as lacunas de integração ainda não aplicáveis nesta fase.
