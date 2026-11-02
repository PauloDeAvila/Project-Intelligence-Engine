# Cloud gateway prerequisite for PIE benchmarks

This branch provides a **GitHub-hosted connectivity smoke test** for the user's 9Router OpenAI-compatible API. It is deliberately separate from the experimental v3 benchmark: a successful gateway probe does **not** imply that the v3 code, evaluation or results are deployed.

## Required configuration

Configure these repository **Actions secrets** through GitHub Settings:

- `PIE_API_BASE_URL`: a reachable **HTTPS** URL forwarding to 9Router's OpenAI-compatible API. A localhost URL (`127.0.0.1:20128`) does not work from GitHub-hosted runners.
- `PIE_API_KEY`: a newly issued inference key. Never commit a key, even to a public repository.

Trigger `PIE - 9Router cloud gateway check` through Actions > Run workflow with an exact model ID. The gateway probe sends a single 64-token-limit question; it does not send repository source code. Its diagnostic artifact does not contain the secret or endpoint URL.

## Security and constraints

GitHub-hosted runners cannot reach the local 9Router process without a separately configured tunnel, reverse proxy or public upstream endpoint. This workflow **does not** install a tunnel on the user's machine, set GitHub secrets or provision cloud infrastructure.

Only after the gateway probe succeeds should the v3 benchmark source and lab fixtures be integrated and regression-tested in a separate PR. Keep benchmarks manually triggered until quota and cost behavior have been validated.

The publicly pasted inference key should be revoked and replaced prior to use.
