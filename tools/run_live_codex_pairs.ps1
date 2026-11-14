<# Explicit paid real Codex paired usage trial. Does not modify configs/auth. #>
param([Parameter(Mandatory=$true)][string]$Workspace,
      [Parameter(Mandatory=$true)][string]$Scenario,
      [Parameter(Mandatory=$true)][string]$BaselineCodexHome,
      [Parameter(Mandatory=$true)][string]$OptimizedCodexHome,
      [string]$OutputDir=(Join-Path $env:USERPROFILE 'pie-live-evidence\provider-usage'),
      [int]$Repetitions=3,[int]$Timeout=240,[string]$PythonExe='py',
      [string]$Prices='')
$ErrorActionPreference='Stop'
if($Repetitions -lt 3 -or $Repetitions -gt 20){throw 'Require 3..20 repetitions'}
if(-not (Test-Path $Scenario) -or -not (Test-Path $Workspace)){throw 'Missing scenario/workspace'}
foreach($homeDir in @($BaselineCodexHome,$OptimizedCodexHome)){
 if(-not (Test-Path (Join-Path $homeDir 'config.toml'))){
  throw "Missing CODEX_HOME/config.toml in $homeDir"
 }
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$records=@()
for($i=1;$i -le $Repetitions;$i++){
 $order=if($i % 2 -eq 0){@('optimized','baseline')}else{@('baseline','optimized')}
 foreach($condition in $order){
  $homeDir=if($condition -eq 'baseline'){$BaselineCodexHome}else{$OptimizedCodexHome}
  $target=Join-Path $OutputDir ("{0}-{1:D2}.json" -f $condition,$i)
  Write-Host "Real Codex run: $condition / $i"
  $captureArgs=@('-m','pie.certification.cli','capture',
   '--scenario',$Scenario,'--workspace',$Workspace,'--codex-home',$homeDir,
   '--condition',$condition,'--repetition',"$i",'--timeout',"$Timeout",
   '--output',$target,'--telemetry-workspace',$Workspace,
   '--telemetry-task-id',($Scenario | Split-Path -LeafBase))
  & $PythonExe @captureArgs
  if($LASTEXITCODE -ne 0){throw 'Provider trace unavailable; NOT_CERTIFIED'}
  $records+=$target
 }
}
$summary=Join-Path $OutputDir 'paired-token-summary.json'
$compareArgs=@('-m','pie.certification.cli','compare','--min-pairs',"$Repetitions",
 '--output',$summary)
if($Prices){$compareArgs+=@('--prices',$Prices)}
$compareArgs+=$records
& $PythonExe @compareArgs
if($LASTEXITCODE -ne 0){throw 'Paired correctness/usage gate failed'}
Write-Host "Provider-reported paired usage: $summary"
