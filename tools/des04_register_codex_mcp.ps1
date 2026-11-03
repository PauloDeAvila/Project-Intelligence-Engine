# Opt-in local Codex MCP registration for an isolated PIE source checkout.
# Default mode is preview-only. -Apply is the sole mutation switch.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [Parameter(Mandatory = $true)]
    [string]$PythonExe,

    [string]$SourceRoot = (Split-Path -Parent $PSScriptRoot),

    [string]$ServerName = 'pie-des04-preview',

    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($ServerName -notmatch '^[A-Za-z0-9_-]{1,64}$') {
    throw 'ServerName must contain only letters, digits, underscore or hyphen.'
}
$project = (Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).Path
$source = (Resolve-Path -LiteralPath $SourceRoot -ErrorAction Stop).Path
$python = (Resolve-Path -LiteralPath $PythonExe -ErrorAction Stop).Path
$module = Join-Path $source 'src\pie\interfaces\mcp_server.py'
$index = Join-Path $project '.pie\index.sqlite3'

if (-not (Test-Path -LiteralPath $module -PathType Leaf)) {
    throw "PIE MCP server module not found in SourceRoot: $module"
}
if (-not (Test-Path -LiteralPath $index -PathType Leaf)) {
    throw "Project is not indexed. Run 'pie init' and 'pie index' in a disposable working copy first: $project"
}
if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw "Codex CLI is not installed or is not available on PATH."
}

$envBackup = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')
try {
    [Environment]::SetEnvironmentVariable('PYTHONPATH', (Join-Path $source 'src'), 'Process')
    & $python -c 'import pie.interfaces.mcp_server; import pie.retrieval.context_pack'
    if ($LASTEXITCODE -ne 0) {
        throw 'Python could not import the experimental PIE package. Check PythonExe and SourceRoot.'
    }
} finally {
    [Environment]::SetEnvironmentVariable('PYTHONPATH', $envBackup, 'Process')
}

# This registration does not start Qwen, invoke Codex inference, or touch the
# HTTP Gateway. Each Codex MCP workspace has one trusted fixed root.
$argsForCodex = @(
    'mcp', 'add', $ServerName,
    '--env', ('PYTHONPATH=' + (Join-Path $source 'src')),
    '--', $python, '-u', '-m', 'pie.interfaces.mcp_server',
    '--root', $project
)

Write-Output "PIE source  : $source"
Write-Output "Project root: $project"
Write-Output "Python      : $python"
Write-Output "MCP server  : $ServerName"
Write-Output ("Command     : codex " + (($argsForCodex | ForEach-Object {
    if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
}) -join ' '))

if (-not $Apply) {
    Write-Output 'PREVIEW ONLY. Run again with -Apply to register the server with Codex.'
    return
}

# Never overwrite or remove an existing MCP entry without separate review.
& codex mcp get $ServerName --json 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    throw "Codex MCP entry '$ServerName' already exists. No changes were made."
}

& codex @argsForCodex
if ($LASTEXITCODE -ne 0) {
    throw "Codex MCP add failed (exit code $LASTEXITCODE)."
}
& codex mcp get $ServerName --json
if ($LASTEXITCODE -ne 0) {
    throw 'Codex add returned success, but retrieving the new entry failed.'
}
Write-Output 'MCP registration completed. Restart the Codex session before querying the PIE tool.'
