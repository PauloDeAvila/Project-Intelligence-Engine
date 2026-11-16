# PIE Phase 3 — OpenAI-compatible harness routing audit

Date: 2026-11-15

## Result

The local OpenAI-compatible endpoint is reachable and can serve a valid chat
completion. It is not currently a DeepSeek endpoint: the model list advertises
`gambiarraapi/glm-5.3-flash`.

The environment file requests `modelo-unlimited`, which is not present in the
advertised model list. That configuration must not be treated as evidence that
DeepSeek was routed.

## Evidence collected

- `GET http://127.0.0.1:8080/v1/models`: returned one model,
  `gambiarraapi/glm-5.3-flash`.
- A single direct `POST /v1/chat/completions` using that advertised model
  returned valid JSON and usage: 15 input tokens and 7 completion tokens.
- A direct request using `deepseek/deepseek-v4-flash-0731free:free` returned
  HTTP 404, so the DeepSeek route is not exposed by the currently running
  gateway.
- The probe included `thinking=false` and `enable_thinking=false`; the
  response had no reasoning content for this minimal request.
- No credentials or response contents were persisted in this report.

## Gateway limitation

`C:\Users\phsra\Downloads\Infinite\core\grserver.py` forwards a fixed set of
OpenAI fields from the request. It does not forward `thinking`,
`enable_thinking`, or `reasoning_effort`. Therefore the previous PIE benchmark
results cannot be interpreted as a controlled provider-level comparison of
reasoning disabled/enabled.

## Certification impact

The harness route is operational, and the strongest valid PIE run remains the
three-pair Web compiled-context experiment with 90.894% local token savings and
all six oracles passing. It is a deterministic local-provider replay, not
Codex certification. The 95% target was not reached, and the official status
remains `NOT_CERTIFIED`.

