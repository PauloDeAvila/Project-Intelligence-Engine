# Isolated Windows paired benchmark: no public tunnel, no personal OpenCode.
# Executa duas instâncias isoladas do OpenCode 2.2.5 na mesma máquina:
#   WITH_PIE   -> OpenCode + Nemotron + MCP do PIE (porta WithPort)
#   WITHOUT_PIE -> OpenCode + Nemotron, sem MCP do PIE (porta WithoutPort)
# Ambas usam o mesmo modelo, mesmo repositório e mesmas perguntas.
# Nenhuma instância pessoal do OpenCode é modificada.
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

function Start-IsolatedOpenCode {
    param(
        [string]$Binary,
        [string]$Config,
        [string]$Password,
        [int]$Port,
        [string]$WorkingDir
    )
    # Cada processo OpenCode recebe seu próprio script .bat temporário que
    # define OPENCODE_CONFIG e OPENCODE_PASSWORD antes de iniciar o servidor.
    # Isso garante:
    #  1. Isolamento de ambiente entre WITH_PIE e WITHOUT_PIE (sem vazamento
    #     de configuração de uma instância para outra).
    #  2. Que o OpenCode 2.2.5 leia as variáveis no bootstrap via .bat, que o
    #     cmd.exe transmite corretamente ao processo filho Node.js.
    $batPath = Join-Path $env:TEMP ("start-opencode-" + [guid]::NewGuid().ToString("N") + ".bat")
    $escapedBinary = $Binary -replace '"', '""'
    $batContent = "@echo off`r`nset OPENCODE_CONFIG=" + $Config + "`r`nset OPENCODE_PASSWORD=" + $Password + "`r`n""" + $escapedBinary + """ serve --hostname 127.0.0.1 --port " + $Port
    $batContent | Out-File -FilePath $batPath -Encoding utf8
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", $batPath) -WorkingDirectory $WorkingDir -PassThru -WindowStyle Hidden
    return @{ Process = $proc; BatPath = $batPath }
}

$procWith = $null
$procWithout = $null
$batWith = $null
$batWithout = $null
try {
    $withPassword = New-TestPassword
    $withoutPassword = New-TestPassword
    $withConfig = Join-Path $dir "with-pie.json"
    $withoutConfig = Join-Path $dir "without-pie.json"

    # Inicialização sequencial: cada instância recebe seu próprio .bat com
    # variáveis de ambiente isoladas. Inicia-se uma por vez para evitar race
    # condition entre as duas inicializações assíncronas.
    $withResult = Start-IsolatedOpenCode -Binary $binary -Config $withConfig -Password $withPassword -Port $WithPort -WorkingDir $root
    $procWith = $withResult.Process
    $batWith = $withResult.BatPath

    # Aguardar o primeiro servidor estar ouvindo antes de iniciar o segundo.
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        if ($procWith.HasExited) { throw "WITH_PIE OpenCode exited during startup" }
        try {
            $socket = [Net.Sockets.TcpClient]::new()
            $socket.Connect("127.0.0.1", $WithPort)
            $socket.Close()
            break
        } catch { Start-Sleep -Milliseconds 400 }
    }

    $withoutResult = Start-IsolatedOpenCode -Binary $binary -Config $withoutConfig -Password $withoutPassword -Port $WithoutPort -WorkingDir $root
    $procWithout = $withoutResult.Process
    $batWithout = $withoutResult.BatPath

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

    # Aguardar que o MCP pie esteja conectado (WITH_PIE) e ausente (WITHOUT_PIE)
    # antes de iniciar o benchmark. A mera abertura da porta TCP não garante que
    # o servidor stdio MCP foi inicializado e registrado na API v2.
    function Wait-McpState {
        param([string]$Url, [string]$Password, [bool]$ExpectPie, [int]$TimeoutSeconds)
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        $auth = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes("opencode:" + $Password))
        $headers = @{"Authorization" = "Basic " + $auth; "Accept" = "application/json"}
        while ((Get-Date) -lt $deadline) {
            try {
                $resp = Invoke-WebRequest -Uri ($Url + "/api/mcp") -Method GET -Headers $headers -ErrorAction Stop -TimeoutSec 5
                $body = $resp.Content | ConvertFrom-Json
                $data = $body.data
                if ($data -is [System.Array]) {
                    $pie = $data | Where-Object { $_.name -eq "pie" }
                    if ($ExpectPie) {
                        if ($pie.Count -eq 1 -and $pie[0].status.status -eq "connected") {
                            return $true
                        }
                    } else {
                        if ($pie.Count -eq 0) {
                            return $true
                        }
                    }
                }
            } catch {
                # Servidor ainda inicializando; tenta novamente.
            }
            Start-Sleep -Milliseconds 500
        }
        return $false
    }

    $withPieReady = Wait-McpState -Url "http://127.0.0.1:$WithPort" -Password $withPassword -ExpectPie $true -TimeoutSeconds 30
    $withoutPieReady = Wait-McpState -Url "http://127.0.0.1:$WithoutPort" -Password $withoutPassword -ExpectPie $false -TimeoutSeconds 30
    if (-not $withPieReady) { throw "WITH_PIE server lacks connected pie MCP" }
    if (-not $withoutPieReady) { throw "WITHOUT_PIE server still exposes pie MCP" }

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
    foreach ($bat in @($batWith, $batWithout)) {
        if ($null -ne $bat -and (Test-Path -LiteralPath $bat)) {
            Remove-Item -LiteralPath $bat -Force -ErrorAction SilentlyContinue
        }
    }
}
