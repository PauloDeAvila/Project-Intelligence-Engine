# Fase 3.16 — plano offline do controlador único

O controlador `pie-phase3-controller` gerou `49-controller-plan.json` com:

- dois cenários determinísticos, Blender e Web;
- `prompt_sha256` e `expected_sha256`, sem persistir prompts no manifesto;
- três repetições por domínio;
- 12 sessões planejadas, seis por domínio;
- lote piloto de quatro sessões e lote complementar de oito;
- `run_id` determinístico por condição/cenário/repetição;
- `pair_id` compartilhado entre os braços do mesmo cenário;
- nenhuma retry automática;
- modo explícito `PLAN_ONLY_NO_MODEL_EXECUTION`.

Os oráculos do manifesto são independentes do texto final do modelo: propriedades de material Blender e referências/textos de uma página Web local. O controlador rejeita cenários sem especificação de oráculo, IDs duplicados, pares incompletos ou orçamento diferente de 12 sessões.

Nenhuma sessão Codex foi iniciada. O plano exige autorização independente para cada lote.
