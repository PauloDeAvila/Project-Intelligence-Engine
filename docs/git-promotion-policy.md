# Git promotion policy

Permanent branches: `testes` → `revisao` → `main`.

1. Development is pushed to `testes`; the Validation Gate CI runs on every push.
2. On success for the **current** testes SHA, the promotion workflow opens/updates a PR from testes into revisao and requests auto-merge when supported by repository settings. Branch protections can block the merge. On CI failure nothing is promoted.
3. A push into revisao opens/updates a PR into main. **No automatic release merge** occurs; a reviewer must approve the exact revision after independent code/impact review and CI.
4. Rejected changes are fixed on testes, and CI runs anew. Never force push or reset branches to hide failures.

## Required GitHub settings (manual owner verification)
- Protect `testes`: no force pushes/deletion; restrict direct changes to authorized developers/automation.
- Protect `revisao`: PR required, required status checks (Project Verification, Windows Compatibility, Starter Unit Tests); no bypass.
- Protect `main`: PR required, all required status checks, one independent approval, dismiss stale approvals, restrict bypass.
- Enable repository auto-merge to allow testes→revisao to advance automatically.
- Allow GitHub Actions to create PRs (Actions > General > Workflow permissions); otherwise PR creation will fail.
- Decide whether to use a dedicated GitHub App to trigger follow-up workflows on bot-created PRs: default GITHUB_TOKEN-created PR events may not trigger other workflows.
- Review GitHub rulesets and apply settings through the GitHub interface; workflows do NOT create or enforce branch protection themselves.

Note: PRs #2 and #3 are still aimed at main. Retarget only after auditing their effects; do not delete outstanding branches.
