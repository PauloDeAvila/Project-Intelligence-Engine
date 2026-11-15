<##
Run one non-interactive Codex probe with an ephemeral Web/Playwright-only
CODEX_HOME and a deterministic localhost fixture. The persistent config is
never modified; only browser_navigate and browser_snapshot are enabled.
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
$runId = "codex-mcp-restricted-web-" + [guid]::NewGuid().ToString("N")
$stdoutPath = Join-Path $outputPath "$runId-codex.jsonl"
$stderrPath = Join-Path $outputPath "$runId-codex.stderr.log"
$metaPath = Join-Path $outputPath "$runId.json"
$profilePath = Join-Path ([IO.Path]::GetTempPath()) $runId
$fixturePath = Join-Path ([IO.Path]::GetTempPath()) "$runId-fixture"
$configPath = Join-Path $homePath "config.toml"
$authPath = Join-Path $homePath "auth.json"
$config = Get-Content -LiteralPath $configPath -Raw
if (-not $config.Contains("[mcp_servers.pie-web-optimized]")) { throw "Persisted pie-web-optimized route is absent" }
if (-not (Test-Path -LiteralPath $authPath)) { throw "Codex auth.json is unavailable; no model session started" }
if (-not (Get-Command -Name $CodexBin -ErrorAction SilentlyContinue)) { throw "Codex executable unavailable" }
$route = [regex]::Match($config, '(?ms)\[mcp_servers\.pie-web-optimized\].*?(?=\r?\n\[|\z)').Value
if ($route -notmatch '"--workspace"\s*,\s*\x27([^\x27]+)\x27') { throw "PIE Web route has no parseable workspace argument" }
$routeWorkspace = [regex]::Match($route, '"--workspace"\s*,\s*\x27([^\x27]+)\x27').Groups[1].Value
$routeWorkspacePath = (Resolve-Path -LiteralPath $routeWorkspace).Path
if ([IO.Path]::GetFullPath($routeWorkspacePath) -ne [IO.Path]::GetFullPath($workspacePath)) { throw "WRONG_WORKSPACE: route=$routeWorkspacePath expected=$workspacePath" }
if ($route -notmatch 'pie\.gateway\.domain' -or $route -notmatch '"--domain"\s*,\s*"web"') { throw "PIE Web route is incomplete" }
$route = $route -replace '(?m)^\s*enabled_tools\s*=.*\r?\n', ''
$route = $route -replace '(?m)^\s*default_tools_approval_mode\s*=.*\r?\n', ''
$profileConfig = @"
model = '$Model'
model_reasoning_effort = 'medium'
approval_policy = 'never'
sandbox_mode = 'read-only'

$route
enabled_tools = ["browser_navigate", "browser_snapshot"]
default_tools_approval_mode = "prompt"

[mcp_servers.pie-web-optimized.tools.browser_navigate]
approval_mode = "approve"

[mcp_servers.pie-web-optimized.tools.browser_snapshot]
approval_mode = "approve"
"@
$fixtureHtml = '<html><head><title>PIE Web Fixture</title></head><body><main><h1>PIE local fixture</h1><button>Inspect materials</button><p>Deterministic browser certification fixture.</p></main></body></html>'
New-Item -ItemType Directory -Force -Path $profilePath,$fixturePath | Out-Null
$server = $null
try {
    Set-Content -LiteralPath (Join-Path $profilePath "config.toml") -Value $profileConfig -Encoding UTF8
    Copy-Item -LiteralPath $authPath -Destination (Join-Path $profilePath "auth.json") -Force
    Set-Content -LiteralPath (Join-Path $fixturePath "index.html") -Value $fixtureHtml -Encoding UTF8
    $env:CODEX_HOME = $profilePath
    $env:PIE_MCP_DIAGNOSTICS_PATH = Join-Path $workspacePath ".pie-live-store\mcp-lifecycle.jsonl"
    $help = (& $CodexBin exec --help 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "Temporary Web profile rejected by codex exec --help" }
    $mcpInfo = (& $CodexBin mcp get pie-web-optimized 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0 -or $mcpInfo -notmatch "pie-web-optimized") { throw "Temporary Web profile MCP registration failed" }
    $python = Join-Path $workspacePath ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) { throw "Project Python executable unavailable" }
    $server = Start-Process -FilePath $python -ArgumentList @("-m","http.server","8766","--bind","127.0.0.1","--directory",$fixturePath) -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 500
    $probeUrl = "http://127.0.0.1:8766/index.html"
    try { $probeResponse = Invoke-WebRequest -Uri $probeUrl -UseBasicParsing -TimeoutSec 5 } catch { throw "Local Web fixture is unreachable: $($_.Exception.Message)" }
    if ($probeResponse.StatusCode -ne 200) { throw "Local Web fixture returned HTTP $($probeResponse.StatusCode)" }
    if ($PreflightOnly) {
        [pscustomobject]@{status="PREFLIGHT_PASS";model_started=$false;quota_consumed=$false;workspace=$workspacePath;route_workspace=$routeWorkspacePath;fixture_url=$probeUrl;enabled_tools=@("browser_navigate","browser_snapshot");other_mcp_servers="disabled_in_profile";approval_policy="never";sandbox="read-only";profile_mcp_get="PASS";fixture_http="PASS"} | ConvertTo-Json -Compress
        return
    }
    $prompt = "Use only pie-web-optimized. Call exactly browser_navigate once with url $probeUrl and browser_snapshot once, in that order. Do not use any other MCP server or tool. Do not click, evaluate JavaScript, submit forms, or access external URLs. Reply with one line per tool containing only the tool name and success/error status."
    $meta = [ordered]@{schema="pie-phase3-codex-restricted-web-probe-v1";run_id=$runId;model=$Model;effort="medium";workspace=$workspacePath;profile=$profilePath;fixture_url=$probeUrl;stdout_path=$stdoutPath;stderr_path=$stderrPath;enabled_tools=@("browser_navigate","browser_snapshot");other_mcp_servers="disabled_in_profile";retries=0;preflight="PASS"}
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
    if ($exitCode -ne 0) { throw "Codex restricted Web probe failed; inspect sanitized artifacts; no retry permitted" }
    Write-Output (Get-Content -LiteralPath $metaPath -Raw)
} finally {
    if ($server) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $profilePath,$fixturePath -Recurse -Force -ErrorAction SilentlyContinue
}
