<# 
Blender multi-choice evidence agent: two real MCP tool schemas per arm,
three candidate fixture objects, deterministic routing by default;
optional strict local Ollama planning is a separate experimental mode.
Runs against the disposable fixture on port 9877, never user artwork.
#>
[CmdletBinding()]
param(
    [string]$Model = 'qwen3:4b',
    [ValidateSet('deterministic','model')][string]$RouteMode = 'deterministic',
    [ValidateRange(1,3)][int]$MaxTasks = 1,
    [ValidateRange(2048,8192)][int]$NumCtx = 8192,
    [ValidateRange(1024,65535)][int]$BlenderPort = 9877,
    [string]$OutputDirectory = $env:TEMP
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$profiles = Join-Path $env:TEMP 'pie-multichoice-blender-profiles'
$profileArgs = @{
    Workspace = $repo
    OutputDirectory = $profiles
    Domain = 'blender'
    BlenderPort = $BlenderPort
    BaselineExposeTool = @('get_scene_info', 'execute_blender_code')
    OptimizedExposeTool = @('pie_blender_query_scene', 'pie_blender_get_object')
}
& (Join-Path $PSScriptRoot 'prepare_phase3_profiles.ps1') @profileArgs
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw 'MCP profile generation failed' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$output = Join-Path $OutputDirectory (
    'pie-blender-multi-choice-{0}.json' -f [guid]::NewGuid().ToString('N').Substring(0,12)
)
$arguments = @(
    (Join-Path $PSScriptRoot 'benchmark_blender_choice_agent.py'),
    '--workspace', $repo,
    '--baseline-profile', (Join-Path $profiles 'pie-phase3-baseline.config.toml'),
    '--optimized-profile', (Join-Path $profiles 'pie-phase3-optimized.config.toml'),
    '--model', $Model,
    '--route-mode', $RouteMode,
    '--num-ctx', [string]$NumCtx,
    '--max-tasks', [string]$MaxTasks,
    '--output', $output
)
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    & $uv.Source run python @arguments
} else {
    & python @arguments
}
if ($LASTEXITCODE -ne 0) {
    throw ('Multi-choice agent failed closed; evidence path: ' + $output)
}
Write-Output ('Multi-choice benchmark report: ' + $output)
