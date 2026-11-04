param([Parameter(Mandatory=$true)][string]$InstallationJournal,[switch]$Commit)
# Guarded removal of this install's three private roots and exact own files.
# Never removes the task/bootstrap/runtime directories, project files or claims.
$ErrorActionPreference='Stop'
function Need([bool]$v,[string]$m){if(-not $v){throw $m}}
function Hash([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function Regular([string]$p){Need (Test-Path -LiteralPath $p -PathType Leaf) "Missing input: $p";for($d=Get-Item -LiteralPath $p;$null -ne $d;$d=$(if($d -is [IO.FileInfo]){$d.Directory}else{$d.Parent})){Need (($d.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) "Reparse input: $p"}}
$file=(Resolve-Path -LiteralPath $InstallationJournal).Path;Regular $file
$j=Get-Content -LiteralPath $file -Raw -Encoding UTF8|ConvertFrom-Json
$dir=Split-Path -Parent $file;$boot=Split-Path -Parent $dir
$cfgFile=Join-Path $boot 'McgsInternalBridge.bridge.json';Regular $cfgFile
Need ((Hash $cfgFile) -eq $j.bootstrap_scope_sha256) 'Journal is not bound to this bootstrap configuration.'
$cfg=Get-Content -LiteralPath $cfgFile -Raw -Encoding UTF8|ConvertFrom-Json
$dest=Join-Path $cfg.addins_directory 'McgsInternalLoader.dll'
Need ([IO.Path]::GetFullPath($dest) -ieq [IO.Path]::GetFullPath($j.wrapper_destination) -and [IO.Path]::GetFullPath($cfg.addins_ini_file) -ieq [IO.Path]::GetFullPath($j.ini_file)) 'Journal file scope differs from its bound config.'
$roots=@('Software\Classes\CLSID\{52119C44-5875-4DA6-9F72-E97D2E2182B4}','Software\Classes\McgsInternalBridge.AddInObj','Software\Classes\TypeLib\{4D2519E0-CC21-4F82-A19C-1AF9801C64E1}')
Need (($j.roots_absent_before -join '|') -ceq ($roots -join '|')) 'Private registration root list differs.'
if(-not $Commit){[ordered]@{action='remove-own-bootstrap';journal=$file;private_roots=$roots;restore_ini_only_if_exact_after=$j.ini_file;delete_only_exact_own_wrapper=$dest;runtime_and_claims_preserved=$true;registry_written=$false;files_changed=$false}|ConvertTo-Json -Depth 12;return}
Need ([Diagnostics.Process]::GetProcessesByName('McgsSetPro').Length -eq 0) 'Close Pro normally before removing this bridge.'
Regular $dest;Regular $j.ini_file;$backup=Join-Path $dir 'Addins.ini.before';Regular $backup
Need ((Hash $dest) -eq $j.wrapper_sha256 -and (Hash $j.ini_file) -eq $j.ini_after_sha256 -and (Hash $backup) -eq $j.ini_before_sha256) 'Own DLL or INI changed; preserve it for review instead of deleting/restoring.'
$expected=@{};foreach($entry in $j.expected_entries){Need (-not $expected.ContainsKey($entry.key)) 'Duplicate journal registry entry.';$expected.Add($entry.key,$entry.values)}
$machine=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine,[Microsoft.Win32.RegistryView]::Registry32)
function CheckTree([string]$path){
 Need ($expected.ContainsKey($path)) "Unplanned private registry subkey: $path"
 $key=$machine.OpenSubKey($path,$false);try{
  Need ($null -ne $key) "Private registry key missing: $path"
  $planned=$expected[$path];$names=@($key.GetValueNames());Need ($names.Count -eq @($planned.PSObject.Properties).Count) "Unplanned/missing registry values: $path"
  foreach($v in $planned.PSObject.Properties){Need ($key.GetValueKind($v.Name) -eq [Microsoft.Win32.RegistryValueKind]::String -and [string]$key.GetValue($v.Name) -ceq [string]$v.Value) "Owned registration value changed: $path"}
  foreach($sub in $key.GetSubKeyNames()){CheckTree ($path+'\'+$sub)}
 }finally{if($null -ne $key){$key.Dispose()}}
}
try{
 foreach($root in $roots){CheckTree $root;$key=$machine.OpenSubKey($root,$false);try{Need ([string]$key.GetValue('CodexBridgeTransactionId') -ceq [string]$j.transaction_id) 'Private root ownership marker changed.'}finally{$key.Dispose()}}
 $result=Join-Path $dir 'removal-result.json';Need (-not(Test-Path -LiteralPath $result)) 'Removal already has an outcome; do not automatically repeat it.'
 $pending=[ordered]@{schema=1;state='prepared_before_removal';installation_journal=$file;transaction_id=$j.transaction_id;runtime_and_claims_preserved=$true}
 [IO.File]::WriteAllText($result,($pending|ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
 foreach($root in $roots){$machine.DeleteSubKeyTree($root,$false)}
 [IO.File]::WriteAllBytes($j.ini_file,[IO.File]::ReadAllBytes($backup))
 Remove-Item -LiteralPath $dest
 Need ((Hash $j.ini_file) -eq $j.ini_before_sha256 -and -not(Test-Path -LiteralPath $dest)) 'Own removal file readback differs.'
 foreach($root in $roots){$key=$machine.OpenSubKey($root,$false);try{Need ($null -eq $key) 'Private registry root remains.'}finally{if($null -ne $key){$key.Dispose()}}}
 $pending.state='removed_owned_registration_and_wrapper';[IO.File]::WriteAllText($result,($pending|ConvertTo-Json),(New-Object Text.UTF8Encoding($false)));$pending|ConvertTo-Json
}finally{$machine.Dispose()}
