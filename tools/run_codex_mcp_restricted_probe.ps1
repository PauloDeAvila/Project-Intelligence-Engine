<##
Run one non-interactive Codex probe with an ephemeral, Blender-only CODEX_HOME.
The persistent config is read but never modified. Only the two read-only Blender
tools are enabled and auto-approved in the temporary profile.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [Parameter(Mandatory=$true)][string]$CodexHome,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [Parameter(Mandatory=$true)][ValidateSet("I_UNDERSTAND_1_MODEL_CALL")][string]$ConfirmQuotaUse,
    [string]$CodexBin = "codex",
    [string]$Model = "gpt-5.6-luna",
    [int]$TimeoutSeconds = 240,
    [switch]$PreflightOnly
)
$ErrorActionPreference = "Stop"
if ($TimeoutSeconds -lt 20 -or $TimeoutSeconds -gt 3600) { throw "TimeoutSeconds must be between 20 and 3600" }
$workspacePath = (Resolve-Path -LiteralPath $Workspace).Path
$homePath = (Resolve-Path -LiteralPath $CodexHome).Path
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
$runId = "codex-mcp-restricted-" + [guid]::NewGuid().ToString("N")
$stdoutPath = Join-Path $outputPath "$runId-codex.jsonl"
$stderrPath = Join-Path $outputPath "$runId-codex.stderr.log"
$metaPath = Join-Path $outputPath "$runId.json"
$profilePath = Join-Path ([IO.Path]::GetTempPath()) $runId
$configPath = Join-Path $homePath "config.toml"
$authPath = Join-Path $homePath "auth.json"
$config = Get-Content -LiteralPath $configPath -Raw
if (-not $config.Contains("[mcp_servers.pie-blender-optimized]")) { throw "Persisted pie-blender-optimized route is absent" }
if (-not (Test-Path -LiteralPath $authPath)) { throw "Codex auth.json is unavailable; no model session started" }
if (-not (Get-Command -Name $CodexBin -ErrorAction SilentlyContinue)) { throw "Codex executable unavailable" }
$route = [regex]::Match($config, '(?ms)\[mcp_servers\.pie-blender-optimized\].*?(?=\r?\n\[|\z)').Value
if ($route -notmatch '"--workspace"\s*,\s*\x27[^\x27]+\x27') { throw "PIE route has no parseable workspace argument" }
$routeWorkspace = [regex]::Match($route, '"--workspace"\s*,\s*\x27([^\x27]+)\x27').Groups[1].Value
$routeWorkspacePath = (Resolve-Path -LiteralPath $routeWorkspace).Path
if ([IO.Path]::GetFullPath($routeWorkspacePath) -ne [IO.Path]::GetFullPath($workspacePath)) { throw "WRONG_WORKSPACE: route=$routeWorkspacePath expected=$workspacePath" }
if ($route -notmatch 'pie\.gateway\.domain' -or $route -notmatch '"--domain"\s*,\s*"blender"') { throw "PIE Blender route is incomplete" }
$route = $route -replace '(?m)^\s*enabled_tools\s*=.*\r?\n', ''
$route = $route -replace '(?m)^\s*default_tools_approval_mode\s*=.*\r?\n', ''
$profileConfig = @"
model = '$Model'
model_reasoning_effort = 'medium'
approval_policy = 'never'
sandbox_mode = 'read-only'

$route
enabled_tools = ["get_addon_status", "get_scene_info"]
default_tools_approval_mode = "prompt"

[mcp_servers.pie-blender-optimized.tools.get_addon_status]
approval_mode = "approve"

[mcp_servers.pie-blender-optimized.tools.get_scene_info]
approval_mode = "approve"
"@
New-Item -ItemType Directory -Force -Path $profilePath | Out-Null
try {
    Set-Content -LiteralPath (Join-Path $profilePath "config.toml") -Value $profileConfig -Encoding UTF8
    Copy-Item -LiteralPath $authPath -Destination (Join-Path $profilePath "auth.json") -Force
    $env:CODEX_HOME = $profilePath
    $env:PIE_MCP_DIAGNOSTICS_PATH = Join-Path $workspacePath ".pie-live-store\mcp-lifecycle.jsonl"
    $help = (& $CodexBin exec --help 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "Temporary profile rejected by codex exec --help" }
    $profileText = Get-Content -LiteralPath (Join-Path $profilePath "config.toml") -Raw
    foreach ($needle in @('enabled_tools', 'default_tools_approval_mode', 'approval_mode = "approve"')) {
        if ($profileText -notmatch [regex]::Escape($needle)) { throw "Temporary profile missing $needle" }
    }
    $mcpInfo = (& $CodexBin mcp get pie-blender-optimized 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0 -or $mcpInfo -notmatch "pie-blender-optimized") { throw "Temporary profile MCP registration failed" }
    if ($PreflightOnly) {
        [pscustomobject]@{status="PREFLIGHT_PASS";model_started=$false;quota_consumed=$false;workspace=$workspacePath;route_workspace=$routeWorkspacePath;enabled_tools=@("get_addon_status","get_scene_info");other_mcp_servers="disabled_in_profile";approval_policy="never";sandbox="read-only";profile_mcp_get="PASS"} | ConvertTo-Json -Compress
        return
    }
    $prompt = "Use only pie-blender-optimized. Call exactly get_addon_status and get_scene_info, once each, in that order. Do not use any other MCP server or tool. Do not modify the Blender scene. Reply with one line per tool containing only the tool name and success/error status."
    $meta = [ordered]@{schema="pie-phase3-codex-restricted-probe-v1";run_id=$runId;model=$Model;effort="medium";workspace=$workspacePath;profile=$profilePath;stdout_path=$stdoutPath;stderr_path=$stderrPath;enabled_tools=@("get_addon_status","get_scene_info");other_mcp_servers="disabled_in_profile";retries=0;preflight="PASS"}
    $meta | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $metaPath -Encoding UTF8
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $codexArgs = @("exec", "--json", "--ephemeral", "--sandbox", "read-only", "--cd", $workspacePath, "--model", $Model, "-")
    $prompt | & $CodexBin @codexArgs 1> $stdoutPath 2> $stderrPath
    $exitCode = $LASTEXITCODE
    $timer.Stop()
    $stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw } else { "" }
    $stderr = $stderr -replace '(?im)(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|cookie|password|secret)\s*[:=].*$', '$1=[REDACTED]'
    $stderr = $stderr -replace '(?i)Bearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer [REDACTED]'
    Set-Content -LiteralPath $stderrPath -Value $stderr -Encoding UTF8
    $events = @(Get-Content -LiteralPath $stdoutPath -ErrorAction SilentlyContinue | Where-Object {$_.Trim()} | ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object {$_})
    $turn = $events | Where-Object {$_.type -eq "turn.completed"} | Select-Object -First 1
    $calls = @($events | Where-Object {$_.type -eq "item.completed" -and $_.item.type -eq "mcp_tool_call"} | ForEach-Object {[ordered]@{server=$_.item.server;tool=$_.item.tool;status=$_.item.status}})
    $meta.exit_code=$exitCode;$meta.duration_ms=$timer.Elapsed.TotalMilliseconds;$meta.provider_usage_status=if($turn -and $turn.usage){"available"}else{"unavailable"};$meta.usage=if($turn){$turn.usage}else{$null};$meta.mcp_tools=$calls;$meta.codex_event_count=$events.Count
    $meta | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $metaPath -Encoding UTF8
    if ($exitCode -ne 0) { throw "Codex restricted probe failed; inspect sanitized artifacts; no retry permitted" }
    Write-Output (Get-Content -LiteralPath $metaPath -Raw)
} finally {
    Remove-Item -LiteralPath $profilePath -Recurse -Force -ErrorAction SilentlyContinue
}
