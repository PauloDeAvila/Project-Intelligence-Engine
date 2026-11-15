<#
Run the separate PIE local MCP/Ollama replay benchmark. Never invokes Codex.
Prerequisite: Blender fixture server or Web fixture HTTP server is running.
#>
[CmdletBinding()]
param(
    [ValidateSet("blender", "web")][string]$Domain = "blender",
    [string]$Model = "qwen3:4b",
    [int]$Repetitions = 3,
    [int]$NumCtx = 16384,
    [int]$BlenderPort = 9877,
    [string]$OutputDirectory = $env:TEMP,
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
}
if ($Domain -eq "blender") {
    $profileArgs.BaselineExposeTool = @("execute_blender_code")
    $profileArgs.OptimizedExposeTool = @("pie_blender_query_scene")
    $profileArgs.BlenderPort = $BlenderPort
} else {
    $profileArgs.BaselineExposeTool = @("browser_navigate", "browser_snapshot")
    $profileArgs.OptimizedExposeTool = @("browser_navigate", "browser_snapshot", "pie_gateway_output_get")
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
    "--output", $report
)
if ($ProbeOnly) {
    $runnerArgs += "--probe-only"
} else {
    $runnerArgs += @("--model", $Model)
}
& python @runnerArgs
if ($LASTEXITCODE -ne 0) {
    throw "Local MCP/Ollama benchmark failed; Codex was not called"
}
Write-Output ("Local benchmark report: " + $report)
