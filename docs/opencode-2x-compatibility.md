# OpenCode 2.2.5 compatibility — corrected contract

**Earlier v1 assumptions in this PR were incorrect.** The authoritative
integration guide is now `docs/opencode-v2-native-api.md`.

OpenCode 2.2.5 uses:
- `mcp.servers.pie` with `type=local` and `command=[python,-m,pie.interfaces.mcp_server,--root,PIE_ROOT]`, NOT `mcp.pie`
- `permissions` as ordered `{action,resource,effect}` rules, NOT a
  `permission` map
- `OPENCODE_PASSWORD` for v2 Basic authentication, NOT
  `OPENCODE_SERVER_PASSWORD`
- `/api/mcp` returning `{location,data:[{name,status:{status:"connected"}}]}`
- `/api/session`, `/api/session/{id}/prompt`,
  `/api/session/active`, `/api/session/{id}/message` rather than
  legacy paths and legacy message parts

These are grounded in official documentation and its OpenAPI JSON:
https://opencode.ai/v2/docs/api
https://opencode.ai/v2/docs/mcp-servers/
https://opencode.ai/v2/docs/permissions/
https://opencode.ai/v2/docs/cli/web

Run the isolated Windows smoke check using the PR's updated
`tools/start_opencode_pie_smoke.ps1`. It stops only its temporary
test server. A live PIE MCP connection and actual model execution are
**still unverified** until the user's Windows instance passes.

Never deploy the old publicly disclosed gateway Bearer. Rotate/revoke
it before exposing a worker. PR #39 remains Draft.
