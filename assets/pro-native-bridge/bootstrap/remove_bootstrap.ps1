param([Parameter(Mandatory=$true)][string]$InstallationJournal,[switch]$Commit)
# Guarded removal of this install's three private roots and exact own files.
# Never removes the task/bootstrap/runtime directories, project files or claims.
$ErrorActionPreference='Stop'
function Need([bool]$v,[string]$m){if(-not $v){throw $m}}
function Hash([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function Regular([string]$p){Need (Test-Path -LiteralPath $p -PathType Leaf) "Missing input: $p"}
function BoundEditorProcesses([string]$p){
 $full=[IO.Path]::GetFullPath($p)
 foreach($proc in [Diagnostics.Process]::GetProcessesByName([IO.Path]::GetFileNameWithoutExtension($full))){try{
  try{$idBefore=$proc.Id;$created=$proc.StartTime.ToUniversalTime();$actual=$proc.MainModule.FileName;if($proc.HasExited){continue};Need ($idBefore -eq $proc.Id -and $created -eq $proc.StartTime.ToUniversalTime()) 'Editor process identity changed during inspection.';if([IO.Path]::GetFullPath($actual) -ieq $full){[ordered]@{pid=$idBefore;created_utc=$created.ToString('o');executable=$actual}}}
  catch{if($proc.HasExited){continue};throw "Cannot inspect candidate editor PID $($proc.Id): $($_.Exception.Message)"}
 }finally{$proc.Dispose()}}
}
$file=(Resolve-Path -LiteralPath $InstallationJournal).Path;Regular $file
$j=Get-Content -LiteralPath $file -Raw -Encoding UTF8|ConvertFrom-Json -AsHashtable
$dir=Split-Path -Parent $file;$boot=Split-Path -Parent $dir
$cfgFile=Join-Path $boot 'McgsInternalBridge.bridge.json';Regular $cfgFile
Need ((Hash $cfgFile) -eq $j.bootstrap_scope_sha256) 'Journal is not bound to this bootstrap configuration.'
$cfg=Get-Content -LiteralPath $cfgFile -Raw -Encoding UTF8|ConvertFrom-Json
$wrapperName='McgsInternalLoader.dll'
if($null -ne $cfg.cold_com_identity){$identity=$cfg.cold_com_identity;Need ($identity.class_guid -cmatch '^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$' -and $identity.type_library_guid -cmatch '^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$' -and $identity.progid -cmatch '^McgsInternalBridge\.AddInObj_[a-f0-9]{10}$' -and $identity.native_wrapper_file_name -cmatch '^McgsInternalLoader_[a-f0-9]{10}\.dll$') 'Cold COM identity differs from its deployment scope.';$wrapperName=[string]$identity.native_wrapper_file_name}
$dest=Join-Path $cfg.addins_directory $wrapperName
Need ([IO.Path]::GetFullPath($dest) -ieq [IO.Path]::GetFullPath($j.wrapper_destination) -and [IO.Path]::GetFullPath($cfg.addins_ini_file) -ieq [IO.Path]::GetFullPath($j.ini_file)) 'Journal file scope differs from its bound config.'
$roots=@('Software\Classes\CLSID\{52119C44-5875-4DA6-9F72-E97D2E2182B4}','Software\Classes\McgsInternalBridge.AddInObj','Software\Classes\TypeLib\{4D2519E0-CC21-4F82-A19C-1AF9801C64E1}')
if($null -ne $cfg.cold_com_identity){$roots=@(('Software\Classes\CLSID\{'+$identity.class_guid+'}'),('Software\Classes\'+$identity.progid),('Software\Classes\TypeLib\{'+$identity.type_library_guid+'}'))}
Need (($j.roots_absent_before -join '|') -ceq ($roots -join '|')) 'Private registration root list differs.'
if(-not $Commit){[ordered]@{action='remove-own-bootstrap';journal=$file;private_roots=$roots;restore_ini_only_if_exact_after=$j.ini_file;delete_only_exact_own_wrapper=$dest;runtime_and_claims_preserved=$true;registry_written=$false;files_changed=$false}|ConvertTo-Json -Depth 12;return}
Need (@(BoundEditorProcesses $cfg.editor_executable).Count -eq 0) 'Close the explicitly bound editor normally before removing this bridge.'
Regular $dest;Regular $j.ini_file;$backup=Join-Path $dir 'Addins.ini.before';Regular $backup
Need ((Hash $dest) -eq $j.wrapper_sha256 -and (Hash $j.ini_file) -eq $j.ini_after_sha256 -and (Hash $backup) -eq $j.ini_before_sha256) 'Own DLL or INI changed; preserve it for review instead of deleting/restoring.'
$expected=@{};foreach($entry in $j.expected_entries){Need (-not $expected.ContainsKey($entry.key)) 'Duplicate journal registry entry.';$expected.Add($entry.key,$entry['values'])}
$hive=if($j.ContainsKey('registry_hive')){[string]$j.registry_hive}else{'HKLM'}
Need ($hive -in @('HKCU','HKLM') -and ($null -eq $cfg.cold_registry_hive -or [string]$cfg.cold_registry_hive -eq $hive)) 'Journal registry hive differs.'
$registryHive=if($hive -eq 'HKCU'){[Microsoft.Win32.RegistryHive]::CurrentUser}else{[Microsoft.Win32.RegistryHive]::LocalMachine}
$machine=[Microsoft.Win32.RegistryKey]::OpenBaseKey($registryHive,[Microsoft.Win32.RegistryView]::Registry32)
function CheckTree([string]$path){
 Need ($expected.ContainsKey($path)) "Unplanned private registry subkey: $path"
 $key=$machine.OpenSubKey($path,$false);try{
  Need ($null -ne $key) "Private registry key missing: $path"
  $planned=$expected[$path];$names=@($key.GetValueNames());Need ($names.Count -eq $planned.Count) "Unplanned/missing registry values: $path"
  foreach($v in $planned.GetEnumerator()){Need ($key.GetValueKind($v.Key) -eq [Microsoft.Win32.RegistryValueKind]::String -and [string]$key.GetValue($v.Key) -ceq [string]$v.Value) "Owned registration value changed: $path"}
  foreach($sub in $key.GetSubKeyNames()){CheckTree ($path+'\'+$sub)}
 }finally{if($null -ne $key){$key.Dispose()}}
}
try{
 foreach($root in $roots){CheckTree $root;$key=$machine.OpenSubKey($root,$false);try{Need ([string]$key.GetValue('CodexBridgeTransactionId') -ceq [string]$j.transaction_id) 'Private root ownership marker changed.'}finally{$key.Dispose()}}
 $result=Join-Path $dir 'removal-result.json';Need (-not(Test-Path -LiteralPath $result)) 'Removal already has an outcome; do not automatically repeat it.'
 $pending=[ordered]@{schema=1;state='prepared_before_removal';installation_journal=$file;transaction_id=$j.transaction_id;runtime_and_claims_preserved=$true}
 [IO.File]::WriteAllText($result,($pending|ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
 Need (@(BoundEditorProcesses $cfg.editor_executable).Count -eq 0) 'The bound editor started during removal preparation; preserve the journal and stop.'
 foreach($root in $roots){$machine.DeleteSubKeyTree($root,$false)}
 [IO.File]::WriteAllBytes($j.ini_file,[IO.File]::ReadAllBytes($backup))
 Remove-Item -LiteralPath $dest
 Need ((Hash $j.ini_file) -eq $j.ini_before_sha256 -and -not(Test-Path -LiteralPath $dest)) 'Own removal file readback differs.'
 foreach($root in $roots){$key=$machine.OpenSubKey($root,$false);try{Need ($null -eq $key) 'Private registry root remains.'}finally{if($null -ne $key){$key.Dispose()}}}
 $pending.state='removed_owned_registration_and_wrapper';[IO.File]::WriteAllText($result,($pending|ConvertTo-Json),(New-Object Text.UTF8Encoding($false)));$pending|ConvertTo-Json
}finally{$machine.Dispose()}
