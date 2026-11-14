<# Check actual Windows RTK, Codex and Blender without paid model calls. #>
param([string]$Repo=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
      [string]$PythonExe='py',[string]$BlenderExe='',
      [string]$OutputDir=(Join-Path $env:USERPROFILE 'pie-live-evidence'))
$ErrorActionPreference='Stop'
New-Item -Force -ItemType Directory -Path $OutputDir | Out-Null
$report=[ordered]@{schema='pie-live-windows-stack-v1';system='Windows';
 rtk_installed=$false;codex_installed=$false;blender_installed=$false;
 blender_headless_passed=$false;rtk_version=$null;codex_version=$null;
 blender_report=$null;route_audit_completed=$false;
 live_codex_usage_measured=$false;
 note='No paid Codex/model request executed by this script'}
foreach($name in @('rtk','codex')){
 $item=Get-Command $name -ErrorAction SilentlyContinue
 if($null -ne $item){
  $report[$name+'_installed']=$true
  $report[$name+'_version']=((& $name --version 2>&1) | Select-Object -First 1) -as [string]
 }
}
if(-not $BlenderExe){
 $item=Get-Command 'blender' -ErrorAction SilentlyContinue
 if($null -ne $item){$BlenderExe=$item.Source}
}
if(-not $BlenderExe){
 $folder='C:\Program Files\Blender Foundation'
 if(Test-Path $folder){
  $found=@(Get-ChildItem $folder -Directory | Sort-Object Name -Descending |
   ForEach-Object{Join-Path $_.FullName 'blender.exe'} | Where-Object{Test-Path $_})
  if($found.Count -gt 0){$BlenderExe=$found[0]}
 }
}
if($BlenderExe -and (Test-Path $BlenderExe)){
 $report.blender_installed=$true
 $script=Join-Path $Repo 'tools\blender_runtime_probe.py'
 $lines=@(& $BlenderExe --background --factory-startup --python $script 2>&1)
 $exitCode=$LASTEXITCODE
 $marker=$lines | Where-Object{$_ -like 'PIE_BLENDER_LIVE_REPORT=*'} | Select-Object -Last 1
 if($marker){
  try{$report.blender_report=$marker.Substring('PIE_BLENDER_LIVE_REPORT='.Length) | ConvertFrom-Json}
  catch{$report.blender_report=$null}
 }
 $report.blender_headless_passed=($exitCode -eq 0 -and
  $null -ne $report.blender_report -and $report.blender_report.state -eq 'PASS')
}
$homeDir=if($env:CODEX_HOME){$env:CODEX_HOME}else{Join-Path $env:USERPROFILE '.codex'}
if(Test-Path (Join-Path $homeDir 'config.toml')){
 $audit=Join-Path $OutputDir 'codex-route-audit.json'
 & $PythonExe -m pie.certification.cli audit --codex-home $homeDir --output $audit | Out-Null
 $report.route_audit_completed=Test-Path $audit
}
$out=Join-Path $OutputDir 'stack-report.json'
$report | ConvertTo-Json -Depth 8 | Out-File -FilePath $out -Encoding utf8
Write-Host "Local evidence: $out"
Write-Host "Blender bpy headless passed: $($report.blender_headless_passed)"
Write-Host 'No Codex provider token measurement by this script.'
if(-not $report.codex_installed -or -not $report.rtk_installed -or
 -not $report.blender_headless_passed){exit 2}
exit 0
