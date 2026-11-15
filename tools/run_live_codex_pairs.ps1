<# Explicit paid real Codex paired usage trial. Does not modify configs/auth. #>
param([Parameter(Mandatory=$true)][string]$Workspace,
      [Parameter(Mandatory=$true)][string]$Scenario,
      [Parameter(Mandatory=$true)][string]$BaselineCodexHome,
      [Parameter(Mandatory=$true)][string]$OptimizedCodexHome,
      [string]$OutputDir=(Join-Path $env:USERPROFILE 'pie-live-evidence\provider-usage'),
      [int]$Repetitions=3,[int]$Timeout=240,[string]$PythonExe='py',
      [string]$Prices='', [string]$BaselineProfile='',
      [string]$OptimizedProfile='',
      [string[]]$BaselineWorkspaces=@(),
      [string[]]$OptimizedWorkspaces=@())
$ErrorActionPreference='Stop'
if($Repetitions -lt 3 -or $Repetitions -gt 20){throw 'Require 3..20 repetitions'}
if(-not (Test-Path $Scenario) -or -not (Test-Path $Workspace)){throw 'Missing scenario/workspace'}
if($BaselineWorkspaces.Count -notin @(0,$Repetitions)){throw 'BaselineWorkspaces must be empty or contain one workspace per repetition'}
if($OptimizedWorkspaces.Count -notin @(0,$Repetitions)){throw 'OptimizedWorkspaces must be empty or contain one workspace per repetition'}
foreach($homeDir in @($BaselineCodexHome,$OptimizedCodexHome)){
 if(-not (Test-Path (Join-Path $homeDir 'config.toml'))){
  throw "Missing CODEX_HOME/config.toml in $homeDir"
 }
}
function Select-RunWorkspace([string]$condition,[int]$repetition){
 $list=if($condition -eq 'baseline'){$BaselineWorkspaces}else{$OptimizedWorkspaces}
 $candidate=if($list.Count -eq 0){$Workspace}else{$list[$repetition-1]}
 if(-not (Test-Path $candidate)){throw "Missing $condition workspace: $candidate"}
 $commit=& git -C $candidate rev-parse HEAD 2>$null
 if($LASTEXITCODE -ne 0 -or -not $commit){throw "Invalid Git workspace: $candidate"}
 $dirty=& git -C $candidate status --porcelain --untracked-files=all
 if($LASTEXITCODE -ne 0 -or $dirty){throw "Workspace is dirty before ${condition} repetition ${repetition}: ${candidate}"}
 return (Resolve-Path -LiteralPath $candidate).Path
}
$commits=@()
foreach($candidate in @($Workspace)+$BaselineWorkspaces+$OptimizedWorkspaces){
 if(Test-Path $candidate){$commits+=(& git -C $candidate rev-parse HEAD 2>$null)}
}
if($commits.Count -gt 1 -and ($commits | Select-Object -Unique).Count -ne 1){throw 'Benchmark workspaces must use the same Git commit'}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$records=@()
for($i=1;$i -le $Repetitions;$i++){
 $order=if($i % 2 -eq 0){@('optimized','baseline')}else{@('baseline','optimized')}
 foreach($condition in $order){
  $homeDir=if($condition -eq 'baseline'){$BaselineCodexHome}else{$OptimizedCodexHome}
  $runWorkspace=Select-RunWorkspace $condition $i
  $target=Join-Path $OutputDir ("{0}-{1:D2}.json" -f $condition,$i)
  Write-Host "Real Codex run: $condition / $i"
  $captureArgs=@('-m','pie.certification.cli','capture',
   '--scenario',$Scenario,'--workspace',$runWorkspace,'--codex-home',$homeDir,
   '--condition',$condition,'--repetition',"$i",'--timeout',"$Timeout",
   '--output',$target,'--telemetry-workspace',$runWorkspace,
   '--telemetry-task-id',($Scenario | Split-Path -LeafBase))
  if($condition -eq 'baseline' -and $BaselineProfile){$captureArgs+=@('--profile',$BaselineProfile)}
  if($condition -eq 'optimized' -and $OptimizedProfile){$captureArgs+=@('--profile',$OptimizedProfile)}
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
