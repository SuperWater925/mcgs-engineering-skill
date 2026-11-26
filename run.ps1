$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE='1'
# PowerShell -File splits an equals-form drive path at the colon before the
# script sees it. Restore only this known option, for dispatch and forwarding.
$normalizedArgs=[Collections.Generic.List[string]]::new()
for($i=0;$i -lt $args.Count;$i++){
 $argument=[string]$args[$i]
 if($argument -match '^--bundle-root=[A-Za-z]$' -and $i+1 -lt $args.Count -and [string]$args[$i+1] -match '^[\\/]'){
  $i++
  $argument += ':'+[string]$args[$i]
 }
 $normalizedArgs.Add($argument)
}
$args=$normalizedArgs.ToArray()
$bundleRoot=$null
$bundleCandidates=[Collections.Generic.List[string]]::new()
$explicitBundle=$null
for($i=0;$i -lt $args.Count;$i++){
 $argument=[string]$args[$i]
 if($argument -eq '--bundle-root'){
  if($i+1 -ge $args.Count -or [string]$args[$i+1] -like '--*'){throw '--bundle-root requires a directory'}
  $i++
  $explicitBundle=[string]$args[$i]
 }elseif($argument.StartsWith('--bundle-root=')){$explicitBundle=$argument.Substring(14)}
}
if($null -ne $explicitBundle){
 if([string]::IsNullOrWhiteSpace($explicitBundle)){throw '--bundle-root requires a directory'}
 $bundleCandidates.Add($explicitBundle)
}
if($env:MCGS_BUNDLE_ROOT){$bundleCandidates.Add($env:MCGS_BUNDLE_ROOT)}
$bundleCandidates.Add($PSScriptRoot)
$bundleCandidates.Add((Split-Path $PSScriptRoot -Parent))
$localRoot=if($env:LOCALAPPDATA){$env:LOCALAPPDATA}else{Join-Path ([Environment]::GetFolderPath('UserProfile')) 'AppData/Local'}
$pointers=@((Join-Path $PSScriptRoot 'turnkey-location.json'),(Join-Path $localRoot 'mcgs-engineering/bundles/current.json'))
foreach($pointer in $pointers){
 if(Test-Path -LiteralPath $pointer){
  try{$location=(Get-Content -LiteralPath $pointer -Raw -Encoding UTF8|ConvertFrom-Json).bundle_root;if($location){$bundleCandidates.Add([string]$location)}}catch{}
 }
}
foreach($candidate in $bundleCandidates){
 try{
  $descriptor=Join-Path $candidate 'bundle.json'
  if(-not(Test-Path -LiteralPath $descriptor -PathType Leaf)){continue}
  $bundle=Get-Content -LiteralPath $descriptor -Raw -Encoding UTF8|ConvertFrom-Json
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
 $nativeArgs=@($args | Select-Object -Skip 1)
 $nativeScript='scripts/pro_native_engineering.py'
 if($nativeArgs.Count -gt 0 -and $nativeArgs[0] -eq '--family'){
  if($nativeArgs.Count -lt 2 -or $nativeArgs[1] -notin @('pro','stu')){throw '--family requires pro or stu'}
  if($nativeArgs[1] -eq 'stu'){$nativeScript='scripts/stu_native_client.py'}
  $nativeArgs=@($nativeArgs | Select-Object -Skip 2)
 }
 & $python -B -X utf8 (Join-Path $PSScriptRoot $nativeScript) @nativeArgs
 exit $LASTEXITCODE
}
if($args.Count -gt 0 -and $args[0] -eq 'native-page-plan'){
 $python=if($env:MCGS_PYTHON){$env:MCGS_PYTHON}else{(Get-Command python -ErrorAction Stop).Source}
 $planArgs=@()
 if($args.Count -gt 1){$planArgs=@($args[1..($args.Count-1)])}
 & $python -B -X utf8 (Join-Path $PSScriptRoot 'scripts/pro_page_plan.py') @planArgs
 exit $LASTEXITCODE
}
if($args.Count -gt 0 -and $args[0] -eq 'native-animation-plan'){
 $python=if($env:MCGS_PYTHON){$env:MCGS_PYTHON}else{(Get-Command python -ErrorAction Stop).Source}
 $animationArgs=@($args | Select-Object -Skip 1)
 & $python -B -X utf8 (Join-Path $PSScriptRoot 'scripts/pro_animation_plan.py') @animationArgs
 exit $LASTEXITCODE
}
if($args.Count -gt 0 -and $args[0] -eq 'native-check-result'){
 $python=if($env:MCGS_PYTHON){$env:MCGS_PYTHON}else{(Get-Command python -ErrorAction Stop).Source}
 $checkArgs=@($args | Select-Object -Skip 1)
 & $python -B -X utf8 (Join-Path $PSScriptRoot 'scripts/native_check_result.py') --powershell (Join-Path $PSHOME 'pwsh.exe') @checkArgs
 exit $LASTEXITCODE
}
if($args.Count -gt 0 -and $args[0] -eq 'native-hwnd'){
 $python=if($env:MCGS_PYTHON){$env:MCGS_PYTHON}else{(Get-Command python -ErrorAction Stop).Source}
 $hwndArgs=@()
 if($args.Count -gt 1){$hwndArgs=@($args[1..($args.Count-1)])}
 & $python -B -X utf8 (Join-Path $PSScriptRoot 'scripts/pro_hwnd.py') @hwndArgs
 exit $LASTEXITCODE
}
if($args.Count -gt 0 -and $args[0] -in @('audit','controls','resources','strategy-source','recipe-cell','normalize-inputs','batch-edit')){
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
# Rebind the shared database command's named parameters through the same
# PowerShell executable. Array splatting into a script treats "-Project"
# and "-Commit" as positional strings.
$pwsh=(Get-Process -Id $PID).Path
& $pwsh -NoProfile -File (Join-Path $PSScriptRoot 'scripts/stu_project.ps1') @args
exit $LASTEXITCODE
