param([Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
$target=[IO.Path]::GetFullPath($Output)
if(Test-Path -LiteralPath $target){throw 'Use a fresh publisher output directory'}
$null=New-Item -ItemType Directory -Path $target
$csc=Join-Path $env:WINDIR 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
$repo=Split-Path $PSScriptRoot -Parent
foreach($entry in @(@('Launcher.cs','McgsStart.exe'),@('InstallerChoice.cs','InstallerChoice.exe'))){
  $source=Join-Path $repo ('assets/turnkey-setup/'+$entry[0])
  $out=Join-Path $target $entry[1]
  $kind=if($entry[0] -eq 'Launcher.cs'){'/target:winexe'}else{'/target:exe'}
  & $csc /nologo $kind /platform:anycpu /optimize+ /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll ('/out:'+$out) $source
  if($LASTEXITCODE -ne 0){throw ('Publisher helper compilation failed: '+$entry[0])}
}
[ordered]@{schema=1;status='publisher_tools_compiled';output=$target;receiver_compilation_required=$false}|ConvertTo-Json
