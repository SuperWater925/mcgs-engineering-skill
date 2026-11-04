$ErrorActionPreference = 'Stop'
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
