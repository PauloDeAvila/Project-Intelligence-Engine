<#
Run the separate PIE local MCP/Ollama replay benchmark. Never invokes Codex.
Prerequisite: Blender fixture server or Web fixture HTTP server is running.
#>
[CmdletBinding()]
param(
    [ValidateSet("blender", "web")][string]$Domain = "blender",
    [ValidateSet("small", "large")][string]$WebVariant = "small",
    [string]$Model = "qwen3:4b",
    [int]$Repetitions = 3,
    [int]$NumCtx = 8192,
    [ValidateRange(800,64000)][int]$PieMaxChars = 2400,
    [ValidateSet("profile", "server")][string]$SchemaScope = "profile",
    [int]$BlenderPort = 9877,
    [ValidateSet("query", "exact")][string]$BlenderMode = "query",
    [string]$NpxExe = "",
    [string]$OutputDirectory = $env:TEMP,
    [switch]$EnableWebRecovery,
    [switch]$ProbeOnly
)
$ErrorActionPreference = "Stop"
if ($Repetitions -lt 1 -or $Repetitions -gt 10) { throw "Repetitions must be 1..10" }
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$profileRoot = Join-Path $env:TEMP ("pie-local-ollama-profiles-" + $Domain)
$scenario = if ($Domain -eq "blender") {
    Join-Path $repo "benchmarks\phase3\blender-selective-task-a-v3-scenario.json"
} else {
    Join-Path $repo "benchmarks\phase3\web-local-page-v2-scenario.json"
}
$profileArgs = @{
    Workspace = $repo
    OutputDirectory = $profileRoot
    Domain = $Domain
    MaxChars = $PieMaxChars
}
if ($Domain -eq "blender") {
    $profileArgs.BaselineExposeTool = @("execute_blender_code")
    $profileArgs.OptimizedExposeTool = if ($BlenderMode -eq "exact") { @("pie_blender_get_object") } else { @("pie_blender_query_scene") }
    $profileArgs.BlenderPort = $BlenderPort
} else {
    $profileArgs.BaselineExposeTool = @("browser_navigate", "browser_snapshot")
    $profileArgs.OptimizedExposeTool = @("browser_navigate", "browser_snapshot")
    if ($EnableWebRecovery) {
        $profileArgs.OptimizedExposeTool += "pie_gateway_output_get"
    }
    $npxCandidate = $null
    if ($NpxExe) {
        $npxCandidate = Get-Command $NpxExe -ErrorAction SilentlyContinue
        if (-not $npxCandidate -and (Test-Path -LiteralPath $NpxExe -PathType Leaf)) {
            $npxCandidate = Get-Item -LiteralPath $NpxExe
        }
    } else {
        $npxCandidate = Get-Command npx.cmd -ErrorAction SilentlyContinue
        if (-not $npxCandidate) {
            foreach ($candidate in @(
                (Join-Path $env:ProgramFiles 'nodejs\\npx.cmd'),
                (Join-Path $env:APPDATA 'npm\\npx.cmd'),
                (Join-Path $env:LOCALAPPDATA 'Programs\\nodejs\\npx.cmd')
            )) {
                if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                    $npxCandidate = Get-Item -LiteralPath $candidate
                    break
                }
            }
        }
    }
    if (-not $npxCandidate) {
        throw 'npx.cmd unavailable. Install Node.js LTS (winget install -e --id OpenJS.NodeJS.LTS), reopen PowerShell, or pass -NpxExe with its full path.'
    }
    $profileArgs.NpxExe = if ($npxCandidate.Source) { $npxCandidate.Source } else { $npxCandidate.FullName }
}
$scenario = if ($Domain -eq "web" -and $WebVariant -eq "large") {
    Join-Path $repo "benchmarks\phase3\web-large-page-scenario.json"
} else {
    $scenario
}
if ($Domain -eq "web") {
    $scenarioDocument = Get-Content -Raw -LiteralPath $scenario | ConvertFrom-Json
    $fixtureUrl = if ($scenarioDocument.fixture_url) {
        [string]$scenarioDocument.fixture_url
    } else {
        "http://127.0.0.1:8766/index.html"
    }
    $fixtureMarker = if ($WebVariant -eq "large") {
        "Entry 099 — material catalog reference CV"
    } else {
        "Inspect materials"
    }
    $forbiddenMarker = if ($WebVariant -eq "small") {
        "Entry 099 — material catalog reference CV"
    } else {
        $null
    }
    try {
        $fixtureBody = (Invoke-WebRequest -Uri $fixtureUrl -UseBasicParsing -TimeoutSec 10).Content
    } catch {
        throw "Web fixture preflight failed for $fixtureUrl before MCP/model execution: $($_.Exception.Message)"
    }
    if (-not $fixtureBody.Contains($fixtureMarker)) {
        throw "Web fixture mismatch for $fixtureUrl before MCP/model execution; expected marker '$fixtureMarker'"
    }
    if ($forbiddenMarker -and $fixtureBody.Contains($forbiddenMarker)) {
        throw "Web fixture mismatch for $fixtureUrl before MCP/model execution; large-fixture marker found in small variant"
    }
}
& (Join-Path $PSScriptRoot "prepare_phase3_profiles.ps1") @profileArgs

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$report = Join-Path $OutputDirectory (
    "pie-{0}-ollama-{1}.json" -f $Domain, [guid]::NewGuid().ToString("N").Substring(0,12)
)
$runnerArgs = @(
    (Join-Path $PSScriptRoot "benchmark_local_ollama.py"),
    "--workspace", $repo,
    "--scenario", $scenario,
    "--baseline-profile", (Join-Path $profileRoot "pie-phase3-baseline.config.toml"),
    "--optimized-profile", (Join-Path $profileRoot "pie-phase3-optimized.config.toml"),
    "--repetitions", ([string]$Repetitions),
    "--num-ctx", ([string]$NumCtx),
    "--schema-scope", $SchemaScope,
    "--blender-mode", $BlenderMode,
    "--output", $report
)
if ($ProbeOnly) {
    $runnerArgs += "--probe-only"
} else {
    $runnerArgs += @("--model", $Model)
}
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    & $uv.Source run python @runnerArgs
} else {
    & python @runnerArgs
}
if ($LASTEXITCODE -ne 0) {
    throw "Local MCP/Ollama benchmark failed; Codex was not called"
}
Write-Output ("Local benchmark report: " + $report)
