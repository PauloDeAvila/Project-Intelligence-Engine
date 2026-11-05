# OpenCode 2.x isolated PIE MCP smoke check. No remote gateway or inference.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PieRoot,
    [int]$Port = 4097,
    [string]$Python = "python",
    [int]$TimeoutSeconds = 45
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $PieRoot).Path
$py = (& $Python -c "import sys; print(sys.executable)").Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to find the PIE Python interpreter" }
$root = [IO.Path]::GetFullPath($root)
$folder = Join-Path $env:LOCALAPPDATA "pie-orchestrator"
[IO.Directory]::CreateDirectory($folder) | Out-Null
$id = [guid]::NewGuid().ToString("N")
$config = Join-Path $folder ("opencode-pie-" + $id + ".json")
$generator = Join-Path $PSScriptRoot "create_opencode_pie_config.py"
& $py $generator --root $root --python $py --output $config
if ($LASTEXITCODE -ne 0) { throw "Failed to generate isolated MCP configuration" }
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) { throw "Port $Port is already in use; refusing to attach to another process" }
$cmd = Get-Command "opencode" -CommandType Application -ErrorAction Stop
$previousConfig = [Environment]::GetEnvironmentVariable("OPENCODE_CONFIG", "Process")
$previousPassword = [Environment]::GetEnvironmentVariable("OPENCODE_SERVER_PASSWORD", "Process")
$previousUsername = [Environment]::GetEnvironmentVariable("OPENCODE_SERVER_USERNAME", "Process")
$server = $null
try {
    $randomBytes = New-Object byte[] 32
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($randomBytes) } finally { $random.Dispose() }
    $env:OPENCODE_SERVER_PASSWORD = [BitConverter]::ToString($randomBytes).Replace("-", "")
    $env:OPENCODE_SERVER_USERNAME = "opencode"
    $env:OPENCODE_CONFIG = $config
    $server = Start-Process -FilePath $cmd.Source -WorkingDirectory $root -ArgumentList @("serve", "--hostname", "127.0.0.1", "--port", "$Port") -PassThru
    $preflight = Join-Path $PSScriptRoot "verify_opencode_runtime.py"
    $url = "http://127.0.0.1:$Port"
    $ready = $false
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($server.HasExited) { throw "Isolated OpenCode exited with code $($server.ExitCode)" }
        try {
            & $py $preflight --url $url --root $root 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        } catch {
            # Transient startup error while booting.
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "Isolated OpenCode did not pass runtime preflight" }
    & $py $preflight --url $url --root $root
    if ($LASTEXITCODE -ne 0) { throw "OpenCode runtime preflight failed" }
    Write-Host "PASS: Isolated OpenCode/MCP contract ready; no model invoked"
}
finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    }
    [Environment]::SetEnvironmentVariable("OPENCODE_CONFIG", $previousConfig, "Process")
    [Environment]::SetEnvironmentVariable("OPENCODE_SERVER_PASSWORD", $previousPassword, "Process")
    [Environment]::SetEnvironmentVariable("OPENCODE_SERVER_USERNAME", $previousUsername, "Process")
}
