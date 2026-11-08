# Alternative GitLab execution without Cloudflare Tunnel (outbound-only)

An absent `~/.cloudflared/cert.pem` blocks certain **locally managed**
Cloudflare operations, not all options. Remotely managed Cloudflare Tunnels
can instead use a dashboard-issued tunnel token, with Cloudflare Access
configured separately. This optional bridge needs **no tunnel at all**.

## Architecture

The Windows PC runs `pie-orchestrator-gitlab-poll`. It queries only the
configured GitLab.com numeric project ID over outbound HTTPS, selecting open
issues labeled `pie-agent-ready`. Issues must also be authored by explicitly
allowlisted numeric GitLab user IDs. The bridge does not send issue titles,
descriptions, comments or arbitrary prompts to OpenCode. It uses a fixed
local policy mapping to one approved project, read-only task type and model.

Each issue IID corresponds to exactly one persistent SQLite idempotency key.
On terminal status, the bridge posts a minimal issue note with the task ID,
status and provider-reported token counters if available, **not the model
response, source contents, errors or credentials**. Existing notes are
checked for the task marker before posting; a single poller instance is
required and delivery is best-effort, not exactly-once under concurrent
writers. A running/failed/restarted task is not automatically retried.

## Setup on the user's machine (not in GitHub)

1. Install the experimental package locally: `python -m pip install -e .`.
2. Copy `docs/opencode-orchestrator.example.json` to a private directory,
   set your absolute project root, SQLite path and OpenCode model ID.
3. Add a `gitlab_poll` object as in
   `docs/gitlab-poll.example.json`, with the **real numeric project ID**,
   **real allowlisted author ID** and the fixed `task` matching your
   local `projects` allowlist.
4. Provide `PIE_GITLAB_API_TOKEN` locally with API read/write rights to
   that exact project. GitLab's token cannot be created from this GitHub PR.
   Use the most restricted project access token and role available for
   listing issues and writing notes. Rotate/revoke on compromise.
5. Start OpenCode **with your local server password and read-only
   permission controls**, as already required by Stage 1. This bridge
   does NOT enforce OpenCode permissions; enabling real model execution
   requires a separate verified host-level tool isolation test.
6. Dry run with a GitLab project containing NO issues with the trigger
   label, then test with one authorized, pre-approved issue:

   ```powershell
   $env:PIE_GITLAB_API_TOKEN = Read-Host "GitLab project token"
   pie-orchestrator-gitlab-poll --config C:\\private\\orchestrator.json
   ```

7. For scheduled polling, run the same command with `--interval 60`
   in one supervised Windows service or scheduled terminal instance.

No inbound firewall rule, router port-forward, Cloudflare DNS record or
Cloudflare origin certificate is required. The PC must be on, logged into
the necessary model provider via OpenCode, and able to reach GitLab.com.

## Validation and limitations

Unit tests stub GitLab and OpenCode, covering allowlists, idempotency,
ignored issue body, publication and no secret disclosure. Full regression
and Pyright run in GitHub CI. These cannot prove remote end-to-end success
on the user's Windows machine. No real GitLab token, Cloudflare token,
Nemotron account or computer access is available in GitHub CI.

This is **a one-agent fixed read-only task bridge**, not a generic remote
shell, permission-safe coding sandbox, multiagent scheduler, or secure
public HTTP ingress. Retain PR as experimental until an end-to-end run
and host-level permission checks are observed. For true push delivery
later, use Cloudflare remotely managed token+Access with authenticated
ingress and a separately authenticated GitLab dispatcher.

## Explicit execution gate

The polling bridge **queues only by default**. It does not automatically
contact the model, and this queue-only mode can safely verify GitLab API
access, filtering and persistence. When a human has independently verified
read-only tool restrictions in their local OpenCode version, they may opt in
with `pie-orchestrator-gitlab-poll --config C:\\private\\orchestrator.json --execute`
(for continuous operation append `--interval 60`). This is a local operator
choice, never a field accepted from a GitLab issue. Without tested permissions,
do not use `--execute`: the existing OpenCode adapter does not yet enforce
read-only via tool-level deny rules.
