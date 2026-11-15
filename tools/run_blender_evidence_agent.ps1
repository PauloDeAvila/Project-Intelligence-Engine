<#
Run bounded Blender evidence-agent A/B via local Ollama.
The model selects only tool/target indices. Facts come from MCP source data.
No Codex calls, paid API, retries, or model-transcribed facts.
#>
[CmdletBinding()]
param(
    [string]$Model = "qwen3:4b",
    [ValidateRange(1,3)][int]$Repetitions = 1,
    [ValidateRange(2048,8192)][int]$NumCtx = 8192,
    [ValidateRange(1024,65535)][int]$BlenderPort = 9877,
    [string]$OutputDirectory = $env:TEMP
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$profiles = Join-Path $env:TEMP 'pie-evidence-agent-blender-profiles'
$profileArgs = @{
    Workspace = $repo
    OutputDirectory = $profiles
    Domain = 'blender'
    BlenderPort = $BlenderPort
    BaselineExposeTool = @('execute_blender_code')
    OptimizedExposeTool = @('pie_blender_get_object')
}
& (Join-Path $PSScriptRoot 'prepare_phase3_profiles.ps1') @profileArgs
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw 'MCP profile generation failed' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$report = Join-Path $OutputDirectory (
    'pie-blender-evidence-agent-{0}.json' -f [guid]::NewGuid().ToString('N').Substring(0,12)
)
$argsList = @(
    (Join-Path $PSScriptRoot 'benchmark_blender_evidence_agent.py'),
    '--workspace', $repo,
    '--scenario', (Join-Path $repo 'benchmarks\phase3\blender-selective-task-a-v3-scenario.json'),
    '--baseline-profile', (Join-Path $profiles 'pie-phase3-baseline.config.toml'),
    '--optimized-profile', (Join-Path $profiles 'pie-phase3-optimized.config.toml'),
    '--model', $Model,
    '--num-ctx', [string]$NumCtx,
    '--repetitions', [string]$Repetitions,
    '--output', $report
)
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    & $uv.Source run python @argsList
} else {
    & python @argsList
}
if ($LASTEXITCODE -ne 0) {
    throw 'Evidence agent failed closed; inspect report if it was written'
}
Write-Output ('Evidence agent report: ' + $report)
