<##
Prepare/run one interactive, read-only Codex MCP probe.
Unlike the non-interactive diagnostic, this uses the interactive CLI so a human
can approve MCP calls. It does not modify config.toml or pass --approve-for-me.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [Parameter(Mandatory=$true)][string]$CodexHome,
    [string]$CodexBin = "codex",
    [string]$Model = "gpt-5.6-luna",
    [ValidateSet("on-request")][string]$ApprovalPolicy = "on-request"
)
$ErrorActionPreference = "Stop"
$workspacePath = (Resolve-Path -LiteralPath $Workspace).Path
$homePath = (Resolve-Path -LiteralPath $CodexHome).Path
$configPath = Join-Path $homePath "config.toml"
$config = Get-Content -LiteralPath $configPath -Raw
if (-not $config.Contains("[mcp_servers.pie-blender-optimized]")) { throw "Persisted pie-blender-optimized route is absent" }
if (-not $config.Contains("[mcp_servers.pie-web-optimized]")) { throw "Persisted pie-web-optimized route is absent" }
if (-not (Get-Command -Name $CodexBin -ErrorAction SilentlyContinue)) { throw "Codex executable unavailable" }
$env:CODEX_HOME = $homePath
$env:PIE_MCP_DIAGNOSTICS_PATH = Join-Path $workspacePath ".pie-live-store\mcp-lifecycle.jsonl"
$prompt = "Use only pie-blender-optimized for Blender. Do not use node_repl or other MCP servers. Call get_addon_status and get_scene_info. Ask for approval for each MCP tool call. Do not change the scene. Reply with the observed tool statuses."
Write-Output "Interactive probe prepared. The next command may request human MCP approval."
Write-Output "Workspace: $workspacePath"
Write-Output "Approval: $ApprovalPolicy"
Write-Output "Sandbox: read-only"
& $CodexBin --no-daemon --cd $workspacePath --model $Model --sandbox read-only --ask-for-approval $ApprovalPolicy $prompt
exit $LASTEXITCODE
