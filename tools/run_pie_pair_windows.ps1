# Isolated Windows paired benchmark: no public tunnel, no personal OpenCode.
[CmdletBinding()]
param(
    [string]$PieRoot = ".",
    [string]$Model = "opencode/nemotron-3.5-super-vl-free",
    [int]$WithPort = 4097,
    [int]$WithoutPort = 4098,
    [int]$TimeoutSeconds = 180
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $PieRoot).Path
$py = (& python -c "import sys; print(sys.executable)").Trim()
if ($LASTEXITCODE -ne 0) { throw "Python interpreter unavailable" }
if ($WithPort -eq $WithoutPort) { throw "Two different ports are required" }
foreach ($port in @($WithPort, $WithoutPort)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port already has a listener; refusing to attach to an existing process"
    }
}
$cmds = @(Get-Command opencode -All -ErrorAction Stop | Where-Object {
    $_.CommandType -eq "Application" -and (Test-Path -LiteralPath $_.Source)
})
if ($cmds.Count -eq 0) { throw "No OpenCode application executable found" }
$binary = $cmds[0].Source
$stamp = [guid]::NewGuid().ToString("N")
$dir = Join-Path $env:LOCALAPPDATA ("pie-bench-" + $stamp)
[IO.Directory]::CreateDirectory($dir) | Out-Null
$generator = Join-Path $PSScriptRoot "create_opencode_pair_configs.py"
& $py $generator --root $root --python $py --outdir $dir
if ($LASTEXITCODE -ne 0) { throw "Failed to create paired configs" }

function New-TestPassword {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [BitConverter]::ToString($bytes).Replace("-", "")
}
$oldConfig = $env:OPENCODE_CONFIG
$oldPass = $env:OPENCODE_PASSWORD
$oldWith = $env:OPENCODE_WITH_PASSWORD
$oldWithout = $env:OPENCODE_WITHOUT_PASSWORD
$procWith = $null
$procWithout = $null
try {
    $env:OPENCODE_WITH_PASSWORD = New-TestPassword
    $env:OPENCODE_WITHOUT_PASSWORD = New-TestPassword
    $env:OPENCODE_CONFIG = Join-Path $dir "with-pie.json"
    $env:OPENCODE_PASSWORD = $env:OPENCODE_WITH_PASSWORD
    $procWith = Start-Process -FilePath $binary -WorkingDirectory $root -ArgumentList @("serve", "--hostname", "127.0.0.1", "--port", "$WithPort") -PassThru -WindowStyle Hidden
    $env:OPENCODE_CONFIG = Join-Path $dir "without-pie.json"
    $env:OPENCODE_PASSWORD = $env:OPENCODE_WITHOUT_PASSWORD
    $procWithout = Start-Process -FilePath $binary -WorkingDirectory $root -ArgumentList @("serve", "--hostname", "127.0.0.1", "--port", "$WithoutPort") -PassThru -WindowStyle Hidden

    $deadline = (Get-Date).AddSeconds(45)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        if ($procWith.HasExited -or $procWithout.HasExited) {
            throw "One of the isolated OpenCode servers exited"
        }
        $sockets = @()
        try {
            foreach ($port in @($WithPort, $WithoutPort)) {
                $socket = [Net.Sockets.TcpClient]::new()
                $socket.Connect("127.0.0.1", $port)
                $sockets += $socket
            }
            $ready = $true
            break
        } catch {
            Start-Sleep -Milliseconds 400
        } finally {
            foreach ($socket in $sockets) { $socket.Dispose() }
        }
    }
    if (-not $ready) { throw "OpenCode servers did not become ready" }

    $questions = Join-Path (Split-Path $PSScriptRoot -Parent) "benchmarks\opencode-pair-questions.json"
    $output = Join-Path $dir "results.json"
    $runnerArgs = @(
        (Join-Path $PSScriptRoot "benchmark_opencode_pair.py"),
        "--root", $root,
        "--model", $Model,
        "--questions", $questions,
        "--output", $output,
        "--with-url", "http://127.0.0.1:$WithPort",
        "--without-url", "http://127.0.0.1:$WithoutPort",
        "--timeout", "$TimeoutSeconds"
    )
    & $py @runnerArgs
    $code = $LASTEXITCODE
    Write-Host "Benchmark result: $output"
    if ($code -ne 0) { throw "Benchmark incomplete/failed (exit $code); inspect result JSON" }
    Write-Host "PASS: Comparable benchmark result ready"
} finally {
    foreach ($proc in @($procWith, $procWithout)) {
        if ($null -ne $proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    $env:OPENCODE_CONFIG = $oldConfig
    $env:OPENCODE_PASSWORD = $oldPass
    $env:OPENCODE_WITH_PASSWORD = $oldWith
    $env:OPENCODE_WITHOUT_PASSWORD = $oldWithout
}
