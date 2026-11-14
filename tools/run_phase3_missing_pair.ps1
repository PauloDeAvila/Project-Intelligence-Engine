<#
Execute exactly one authorized baseline/optimized pair for one scenario.
This script never retries and requires an explicit two-call confirmation token.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [Parameter(Mandatory=$true)][string]$Scenario,
    [Parameter(Mandatory=$true)][string]$BaselineCodexHome,
    [Parameter(Mandatory=$true)][string]$OptimizedCodexHome,
    [Parameter(Mandatory=$true)][string]$BaselineProfile,
    [Parameter(Mandatory=$true)][string]$OptimizedProfile,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [Parameter(Mandatory=$true)][ValidateSet("I_UNDERSTAND_2_MODEL_CALLS")][string]$ConfirmQuotaUse,
    [int]$Repetition = 4,
    [int]$Timeout = 240,
    [string]$PythonExe = "py"
)
$ErrorActionPreference = "Stop"
if ($Repetition -lt 1) { throw "Repetition must be positive" }
if (-not (Test-Path -LiteralPath $Workspace) -or -not (Test-Path -LiteralPath $Scenario)) { throw "Workspace or scenario missing" }
if (-not (Test-Path -LiteralPath (Join-Path $BaselineCodexHome ($BaselineProfile + ".config.toml"))) -or
    -not (Test-Path -LiteralPath (Join-Path $OptimizedCodexHome ($OptimizedProfile + ".config.toml")))) {
    throw "Both profile overlays must exist before execution"
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$scenarioId = [IO.Path]::GetFileNameWithoutExtension($Scenario)
$order = @("optimized", "baseline")
foreach ($condition in $order) {
    $homeDir = if ($condition -eq "baseline") { $BaselineCodexHome } else { $OptimizedCodexHome }
    $profile = if ($condition -eq "baseline") { $BaselineProfile } else { $OptimizedProfile }
    $target = Join-Path $OutputDirectory ("{0}-{1:D2}.json" -f $condition, $Repetition)
    $args = @("-m", "pie.certification.cli", "capture", "--scenario", $Scenario,
        "--workspace", $Workspace, "--codex-home", $homeDir, "--condition", $condition,
        "--repetition", "$Repetition", "--timeout", "$Timeout", "--profile", $profile,
        "--telemetry-workspace", $Workspace, "--telemetry-task-id", $scenarioId,
        "--output", $target)
    & $PythonExe @args
    if ($LASTEXITCODE -ne 0) { throw "Capture failed for $condition; no retry is permitted" }
}
Write-Output "PAIR_COMPLETE scenario=$scenarioId repetition=$Repetition output=$OutputDirectory calls=2"
