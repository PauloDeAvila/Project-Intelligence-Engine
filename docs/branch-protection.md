# Enforce branch protection on each new repository

GitHub Actions workflows alone do not block direct pushes or merges. Branch rules are repository settings and are NOT inherited when using a template.

1. Create the project and configure ci/checks.json with real commands for each tier. Give factual reasons for non-applicable tiers.
2. Run python -m unittest discover -s tests and python tools/verify_project.py. Confirm CI jobs really run.
3. Open GitHub > Repository > Settings > Rules > Rulesets (or Settings > Branches).
4. Add an active branch ruleset targeting main. Require pull requests before merging; require status checks to pass. Select the actual CI check context **Project Verification**; require up-to-date branches where appropriate.
5. Restrict bypass permissions. Configure review approvals according to team size and plan capabilities. Independent agent review is documented, but a GitHub review approval may require an actual authorized reviewer.
6. Test enforcement: create a test PR that deliberately fails a check and confirm merge is blocked; then test a passing PR. Ensure direct pushes are restricted as intended.
7. Record the ruleset link, checks, settings and evidence in the new project's PROJECT.md.

If the account, GitHub plan, app permissions or API does not support enforcement, mark bootstrap BLOCKED. Do not claim protection is enabled.

Current repository evidence (2026-11-05): the active `Protect main` ruleset requires a PR and the Phase 0/1/2/3 verification checks, blocks deletion and non-fast-forward updates, has no bypass actors, and requires **zero human approvals**. The Phase 4 checks must be added only after its PR exposes their exact contexts: `Web Relevance Gate (ubuntu-latest)` and `Web Relevance Gate (windows-latest)`. A deliberately failing PR has not been used to prove merge enforcement; do not infer that result from the configuration alone.

Security: never run secrets on untrusted pull requests. Prefer least privilege read-only workflow tokens.
