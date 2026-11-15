<#
Run exactly one instrumented Codex/MCP diagnostic call.

The script intentionally uses the persisted MCP route and never passes array
configuration through `codex -c`; this avoids converting TOML args sequences to
strings. It does not edit config.toml, install dependencies, retry, or run A/B.
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
    [ValidateSet("never", "on-request", "untrusted", "unless-trusted")]
    [string]$ApprovalPolicy = "never",
    [switch]$ApproveForMe
)
$ErrorActionPreference = "Stop"
if ($TimeoutSeconds -lt 20 -or $TimeoutSeconds -gt 3600) { throw "TimeoutSeconds must be between 20 and 3600" }
$workspacePath = (Resolve-Path -LiteralPath $Workspace).Path
$homePath = (Resolve-Path -LiteralPath $CodexHome).Path
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
$runId = "codex-mcp-diagnostic-" + [guid]::NewGuid().ToString("N")
$diagPath = Join-Path $outputPath "$runId-mcp-lifecycle.jsonl"
$stdoutPath = Join-Path $outputPath "$runId-codex.jsonl"
$stderrPath = Join-Path $outputPath "$runId-codex.stderr.log"
$metaPath = Join-Path $outputPath "$runId.json"
$configPath = Join-Path $homePath "config.toml"
$config = Get-Content -LiteralPath $configPath -Raw
if (-not $config.Contains("[mcp_servers.pie-blender-optimized]")) { throw "Persisted pie-blender-optimized route is absent" }
if (-not (Get-Command -Name $CodexBin -ErrorAction SilentlyContinue)) { throw "Codex executable unavailable" }
$auth = (& $CodexBin login status 2>&1) -join " "
if ($LASTEXITCODE -ne 0 -or $auth -notmatch "Logged in") { throw "Codex authentication preflight failed" }
$routeArgs = [regex]::Match($config, '(?ms)\[mcp_servers\.pie-blender-optimized\].*?(?=\r?\n\[|\z)').Value
if ($routeArgs -notmatch "pie\.gateway\.domain" -or $routeArgs -notmatch "--workspace") { throw "PIE Blender gateway route is incomplete" }
$env:CODEX_HOME = $homePath
$env:PIE_MCP_DIAGNOSTICS_PATH = $diagPath
$prompt = "Use only the MCP server named pie-blender-optimized for Blender. Do not use node_repl or any other MCP server. Inspect the current scene with the Blender MCP tools. Read the selected object's material and its Principled BSDF roughness and metallic values. Reply with exactly this single line and nothing else: PIE_BLENDER_DIAGNOSTIC_ORACLE_44"
$meta = [ordered]@{schema="pie-phase3-codex-mcp-diagnostic-v1";run_id=$runId;model=$Model;workspace=$workspacePath;codex_home=$homePath;diagnostics_path=$diagPath;stdout_path=$stdoutPath;stderr_path=$stderrPath;retries=0;preflight="PASS"}
$meta | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $metaPath -Encoding UTF8
$timer = [Diagnostics.Stopwatch]::StartNew()
$codexArgs = @("exec", "--json", "--ephemeral", "--sandbox", "read-only",
    "--cd", $workspacePath, "--model", $Model,
    "-c", "approval_policy=`"$ApprovalPolicy`"")
if ($ApproveForMe) { $codexArgs += "--approve-for-me" }
$codexArgs += "-"
$prompt | & $CodexBin @codexArgs 1> $stdoutPath 2> $stderrPath
$exitCode = $LASTEXITCODE
$timer.Stop()
$stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw } else { "" }
$stderr = $stderr -replace '(?im)(authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|cookie|password|secret)\s*[:=].*$', '$1=[REDACTED]'
$stderr = $stderr -replace '(?i)Bearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer [REDACTED]'
Set-Content -LiteralPath $stderrPath -Value $stderr -Encoding UTF8
$codexEvents = @()
if (Test-Path -LiteralPath $stdoutPath) {
    $codexEvents = @(Get-Content -LiteralPath $stdoutPath | Where-Object { $_.Trim() } | ForEach-Object {
        try { $_ | ConvertFrom-Json } catch { $null }
    } | Where-Object { $_ })
}
$turn = $codexEvents | Where-Object { $_.type -eq "turn.completed" } | Select-Object -First 1
$toolSummary = @($codexEvents | Where-Object {
    $_.type -eq "item.completed" -and $_.item.type -eq "mcp_tool_call"
} | ForEach-Object {
    [ordered]@{server=$_.item.server;tool=$_.item.tool;status=$_.item.status}
})
$meta.exit_code = $exitCode
$meta.duration_ms = $timer.Elapsed.TotalMilliseconds
$meta.provider_usage_status = if ($turn -and $turn.usage) { "available" } else { "unavailable" }
$meta.approval_policy = $ApprovalPolicy
$meta.approve_for_me = [bool]$ApproveForMe
$meta.usage = if ($turn) { $turn.usage } else { $null }
$meta.mcp_tools = $toolSummary
$meta.codex_event_count = $codexEvents.Count
$meta | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $metaPath -Encoding UTF8
if ($exitCode -ne 0) { throw "Codex diagnostic failed; inspect sanitized artifacts; no retry permitted" }
Write-Output (Get-Content -LiteralPath $metaPath -Raw)
