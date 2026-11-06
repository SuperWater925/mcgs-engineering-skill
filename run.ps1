$ErrorActionPreference = 'Stop'
$bundleRoot=$null
$bundleCandidates=[Collections.Generic.List[string]]::new()
if($env:MCGS_BUNDLE_ROOT){$bundleCandidates.Add($env:MCGS_BUNDLE_ROOT)}
$bundleCandidates.Add($PSScriptRoot)
$bundleCandidates.Add((Split-Path $PSScriptRoot -Parent))
$localRoot=if($env:LOCALAPPDATA){$env:LOCALAPPDATA}else{Join-Path ([Environment]::GetFolderPath('UserProfile')) 'AppData/Local'}
$pointers=@((Join-Path $PSScriptRoot 'turnkey-location.json'),(Join-Path $localRoot 'mcgs-engineering/bundles/current.json'))
foreach($pointer in $pointers){
 if(Test-Path -LiteralPath $pointer){
  try{$location=(Get-Content -LiteralPath $pointer -Raw|ConvertFrom-Json).bundle_root;if($location){$bundleCandidates.Add([string]$location)}}catch{}
 }
}
foreach($candidate in $bundleCandidates){
 try{
  $descriptor=Join-Path $candidate 'bundle.json'
  if(-not(Test-Path -LiteralPath $descriptor -PathType Leaf)){continue}
  $bundle=Get-Content -LiteralPath $descriptor -Raw|ConvertFrom-Json
  if($bundle.schema -ne 'mcgs-turnkey-bundle/v1'){continue}
  $candidatePython=Join-Path $candidate $bundle.python
  $candidatePwsh=Join-Path $candidate $bundle.powershell
  if(-not(Test-Path -LiteralPath $candidatePython -PathType Leaf) -or -not(Test-Path -LiteralPath $candidatePwsh -PathType Leaf)){continue}
  $bundleRoot=$candidate;break
 }catch{}
}
if($bundleRoot){
 $env:MCGS_PYTHON=$candidatePython
 $env:MCGS_PWSH=$candidatePwsh
 $env:MCGS_BUNDLE_ROOT=$bundleRoot
 if($PSVersionTable.PSVersion.Major -lt 7){
  & $env:MCGS_PWSH -NoProfile -File $PSCommandPath @args
  exit $LASTEXITCODE
 }
}
if($args.Count -gt 0 -and $args[0] -eq 'turnkey'){
 $python=if($env:MCGS_PYTHON){$env:MCGS_PYTHON}else{(Get-Command python -ErrorAction Stop).Source}
 $setupArgs=@()
 if($args.Count -gt 1){$setupArgs=@($args[1..($args.Count-1)])}
 & $python -B -X utf8 (Join-Path $PSScriptRoot 'scripts/turnkey.py') @setupArgs
 exit $LASTEXITCODE
}
if($args.Count -gt 0 -and $args[0] -eq 'native-engine-select'){
 $python=if($env:MCGS_PYTHON){$env:MCGS_PYTHON}else{(Get-Command python -ErrorAction Stop).Source}
 $selectionArgs=@()
 if($args.Count -gt 1){$selectionArgs=@($args[1..($args.Count-1)])}
 & $python -B -X utf8 (Join-Path $PSScriptRoot 'assets/pro-native-bridge/bootstrap/select_engine.py') @selectionArgs
 exit $LASTEXITCODE
}
if($args.Count -gt 0 -and $args[0] -eq 'native-abi'){
 $python=if($env:MCGS_PYTHON){$env:MCGS_PYTHON}else{(Get-Command python -ErrorAction Stop).Source}
 $locatorArgs=@()
 $locatorScript='assets/pro-native-bridge/abi-adapter/abi_locator.py'
 if($args.Count -gt 1 -and $args[1] -eq 'report'){
  $locatorScript='assets/pro-native-bridge/abi-adapter/adaptive_report.py'
  if($args.Count -gt 2){$locatorArgs=@($args[2..($args.Count-1)])}
 }elseif($args.Count -gt 1){$locatorArgs=@($args[1..($args.Count-1)])}
 & $python -B -X utf8 (Join-Path $PSScriptRoot $locatorScript) @locatorArgs
 exit $LASTEXITCODE
}
if($args.Count -gt 0 -and $args[0] -eq 'new-window'){
 $windowArgs=@()
 if($args.Count -gt 1){$windowArgs=@($args[1..($args.Count-1)])}
 $pwsh=(Get-Process -Id $PID).Path
 & $pwsh -NoProfile -File (Join-Path $PSScriptRoot 'tools/新增窗口事务.ps1') @windowArgs
 exit $LASTEXITCODE
}
if($args.Count -gt 0 -and $args[0] -eq 'native-doctor'){
 $python=if($env:MCGS_PYTHON){$env:MCGS_PYTHON}else{(Get-Command python -ErrorAction Stop).Source}
 $doctorArgs=@()
 if($args.Count -gt 1){$doctorArgs=@($args[1..($args.Count-1)])}
 $env:MCGS_PWSH=(Get-Process -Id $PID).Path
 & $python -B -X utf8 (Join-Path $PSScriptRoot 'scripts/pro_native_doctor.py') @doctorArgs
 exit $LASTEXITCODE
}
if($args.Count -gt 0 -and $args[0] -eq 'native-engineering'){
 $python=if($env:MCGS_PYTHON){$env:MCGS_PYTHON}else{(Get-Command python -ErrorAction Stop).Source}
 $nativeArgs=@()
 if($args.Count -gt 1){$nativeArgs=@($args[1..($args.Count-1)])}
 & $python -B -X utf8 (Join-Path $PSScriptRoot 'scripts/pro_native_engineering.py') @nativeArgs
 exit $LASTEXITCODE
}
if($args.Count -gt 0 -and $args[0] -in @('audit','controls','strategy-source','recipe-cell','normalize-inputs','batch-edit')){
 $python=if($env:MCGS_PYTHON){$env:MCGS_PYTHON}else{(Get-Command python -ErrorAction Stop).Source}
 & $python -B -X utf8 (Join-Path $PSScriptRoot 'scripts/native_tool.py') @args
 exit $LASTEXITCODE
}
if($args.Count -gt 0 -and $args[0] -in @('create','edit','demo')){
 $python=if($env:MCGS_PYTHON){$env:MCGS_PYTHON}else{(Get-Command python -ErrorAction Stop).Source}
 $env:MCGS_PWSH=(Get-Process -Id $PID).Path
 & $python -B -X utf8 (Join-Path $PSScriptRoot 'assets/pro-3.5-cli/scripts/mcgs_file.py') @args
 exit $LASTEXITCODE
}
& (Join-Path $PSScriptRoot 'scripts/stu_project.ps1') @args
if(-not $?){exit 1}
exit 0
