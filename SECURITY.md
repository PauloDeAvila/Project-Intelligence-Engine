# Security policy

## Scope

Security issues include credential exposure, cross-session data access,
unauthorized browser actions, prompt injection that changes execution policy,
and unsafe GitHub Actions behavior.

## Reporting

Do not publish secrets or exploit details in a public issue. Prefer GitHub's
private security advisory flow when it is enabled for this repository:

<https://github.com/PauloDeAvila/Project-Intelligence-Engine/security/advisories/new>

If private reporting is unavailable, contact the repository owner privately
through [PauloDeAvila's GitHub profile](https://github.com/PauloDeAvila) and
request a private channel. Do not put credentials, exploit payloads, or
private project data in a public issue.

## Development rules

- Pull-request CI must not expose API secrets to untrusted code.
- Browser and network capabilities remain opt-in and must be isolated by policy.
- Page content is untrusted data and must not change authorization decisions.
- Security-sensitive changes require independent review and regression evidence.
