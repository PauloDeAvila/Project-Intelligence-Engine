# PIE Domain Gateway: Blender + Web

Two opt-in domain profiles only. Existing PR dependency order:
#63 → #64 → #65 → #72 → #77 → #81.

## What is actually implemented?

**Blender:** Existing Blender MCP bridge is launched as an inner stdio
server. It keeps pie_blender_scene_delta, pie_blender_expand, get_scene_info,
get_object_info and all original Blender tools. Editing a material happens
only in the upstream Blender MCP process, never in the PIE reducer. Unknown
Blender tools and responses are not rewritten.

**Web:** One Playwright MCP stdio server is wrapped by the PIE web profile.
For a successful recognizable accessibility snapshot from a known tool,
the returned text is reduced to a bounded preview of headings and native
element references. Original references such as ref=e2 remain intact for
included elements. Omitted parts can be fetched with
pie_gateway_output_get by using output_id. The response is always explicitly
PARTIAL and UNTRUSTED_PAGE_DATA, and does not imply permission to click.

The web profile accepts known Playwright observation/action snapshot
responses such as browser_snapshot, browser_navigate, browser_click,
browser_type, and browser_wait_for. It NEVER invokes the action a second
time for summarization. It does not rewrite responses from browser_evaluate,
network request body inspectors, screenshots, arbitrary JS, file uploads,
or non-allowlisted tools.

Errors, images, multiple content blocks, structuredContent, outputSchema,
sensitive-surface signals and unexpected formats pass through intact.
An original over 500,000 characters also passes through to avoid claiming
recovery that cannot be provided. Sanitization and secret detection are
best-effort, not a privacy/DLP guarantee.

## One-time setup (Windows PowerShell)

First checkout the exact domain branch (PR #81) after its base PRs are available:

    git fetch origin
    git switch feat/pie-blender-web-domain-gateway-20261114
    py -3.12 -m pip install -e .

Check the TWO commands that normally launch your existing servers.
Use those exact existing commands as upstream arguments. The examples below
are illustrative; do not change them blindly if your servers use custom
environments, API keys, cwd, or authentication.

Blender dry-run, then optional explicit registration:

    pie-domain register --domain blender --name pie-blender-optimized -- uvx mcp-for-blender
    pie-domain register --domain blender --name pie-blender-optimized --apply -- uvx mcp-for-blender

Playwright Web dry-run, then optional explicit registration:

    pie-domain register --domain web --name pie-web-optimized -- npx @playwright/mcp@0.0.85
    pie-domain register --domain web --name pie-web-optimized --apply -- npx @playwright/mcp@0.0.85

On Windows, some Node installations require npx.cmd rather than npx when
launching with shell=False; use the actual executable returned by Get-Command.

To verify the new registrations:

    codex mcp get pie-blender-optimized
    codex mcp get pie-web-optimized

**Existing MCP entries are not overwritten or removed automatically.**
Registering a second name does not transparently intercept calls through
the original server. Switch the client/tool selection to the optimized
registration only after it has been validated, and back up any config before
manually removing or disabling old entries. Retain credentials/permissions.

## Local end-to-end tests (no model tokens)

    py -3.12 -m unittest discover -s tests -p test_pie_domain_gateway.py -v

The synthetic MCP tests exercise browser navigation once, page references,
server response recovery, screenshot pass-through, web errors, output schema
pass-through, and Blender material edit outputs. GitHub CI runs Linux/Windows.

The real browser CI starts an actual Microsoft Playwright MCP server in
headless Chrome, opens a local HTTP page at 127.0.0.1 and checks that the
snapshot is reduced without losing target refs. This performs NO model
request. Its report is saved as a GitHub workflow artifact.

The already validated separate Blender test creates actual materials in
Blender 5.0.1 headless and observes Roughness 0.35 -> 0.28. This does
not prove a live Windows Blender GUI session or remote browsing.

## Metrics, honest limits

The gateway records per-workspace character counts, not provider token usage.
To measure actual savings in Codex use the paired live harness from PR #77,
including a realistic tool-use scenario that calls the optimized MCP entries.
A reduction measured on one page is not a guarantee for all websites.

This is NOT a network-wide intercepting proxy, Chrome extension, web.run
interceptor, or universal Codex browser hook. Only clients using the new
MCP entries are covered. HTTP-based MCP servers need a separate transport
adapter and are deliberately outside this release.

Playwright MCP can generate fresh snapshots automatically after navigation
or click. The PIE web profile reduces these returned snapshots, not
only explicit browser_snapshot calls. Screenshots remain image data.
