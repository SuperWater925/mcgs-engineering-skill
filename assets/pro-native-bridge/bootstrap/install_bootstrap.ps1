param([Parameter(Mandatory=$true)][string]$PreparedRoot,[switch]$Commit)
# Default: print the exact installation plan. -Commit is a separate, explicit
# future deployment command; neither prepare nor build invokes this script.
$ErrorActionPreference='Stop'
$boot=(Resolve-Path -LiteralPath $PreparedRoot).Path
function Hash([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function Need([bool]$v,[string]$m){if(-not $v){throw $m}}
function Regular([string]$p){Need (Test-Path -LiteralPath $p -PathType Leaf) "Missing input: $p"}
function BoundEditorProcesses([string]$p){
 $full=[IO.Path]::GetFullPath($p)
 foreach($proc in [Diagnostics.Process]::GetProcessesByName([IO.Path]::GetFileNameWithoutExtension($full))){try{
  try{$idBefore=$proc.Id;$created=$proc.StartTime.ToUniversalTime();$actual=$proc.MainModule.FileName;if($proc.HasExited){continue};Need ($idBefore -eq $proc.Id -and $created -eq $proc.StartTime.ToUniversalTime()) 'Editor process identity changed during inspection.';if([IO.Path]::GetFullPath($actual) -ieq $full){[ordered]@{pid=$idBefore;created_utc=$created.ToString('o');executable=$actual}}}
  catch{if($proc.HasExited){continue};throw "Cannot inspect candidate editor PID $($proc.Id): $($_.Exception.Message)"}
 }finally{$proc.Dispose()}}
}
$configFile=Join-Path $boot 'McgsInternalBridge.bridge.json';Regular $configFile
$cfg=Get-Content -LiteralPath $configFile -Raw -Encoding UTF8|ConvertFrom-Json
$cold=$cfg.cold_runtime
if($null-eq$cold){$cold=[pscustomobject]@{preload_section='预装载构件';ini_encoding='auto';ini_no_bom_encoding='cp936';startup=[pscustomobject]@{value_name='Count';accepted_values=@(0,1);scan_value=0}}}
$mf=Get-Content -LiteralPath (Join-Path $boot 'build-manifest.json') -Raw -Encoding UTF8|ConvertFrom-Json
Need ($mf.bootstrap_scope_sha256 -eq (Hash $configFile)) 'Bound configuration changed.'
Need ([IO.Path]::GetFullPath($cfg.bootstrap_root) -ieq $boot) 'Prepared bootstrap directory changed.'
foreach($r in $mf.files){$file=Join-Path $boot $r.relative_path;Regular $file;Need ((Hash $file) -eq $r.sha256) "Built file changed: $file"}
$iniHelper=Join-Path $boot 'cold-ini.ps1';Regular $iniHelper;. $iniHelper
$contract=Get-Content -LiteralPath (Join-Path $boot 'prepared-registration-contract.json') -Raw -Encoding UTF8|ConvertFrom-Json -AsHashtable
Need ($contract.state -eq 'prepared_not_registered' -and $contract.bootstrap_scope_sha256 -eq (Hash $configFile) -and $contract.hive -in @('HKCU','HKLM')) 'Registration contract changed.'
$wrapperName='McgsInternalLoader.dll'
$roots=@('Software\Classes\CLSID\{52119C44-5875-4DA6-9F72-E97D2E2182B4}','Software\Classes\McgsInternalBridge.AddInObj','Software\Classes\TypeLib\{4D2519E0-CC21-4F82-A19C-1AF9801C64E1}')
if($null -ne $cfg.cold_com_identity){$identity=$cfg.cold_com_identity;Need ($identity.class_guid -cmatch '^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$' -and $identity.type_library_guid -cmatch '^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$' -and $identity.progid -cmatch '^McgsInternalBridge\.AddInObj_[a-f0-9]{10}$' -and $identity.native_wrapper_file_name -cmatch '^McgsInternalLoader_[a-f0-9]{10}\.dll$') 'Cold COM identity differs from its deployment scope.';$roots=@(('Software\Classes\CLSID\{'+$identity.class_guid+'}'),('Software\Classes\'+$identity.progid),('Software\Classes\TypeLib\{'+$identity.type_library_guid+'}'));$wrapperName=[string]$identity.native_wrapper_file_name}
Need (($contract.roots -join '|') -ceq ($roots -join '|')) 'Private registry scope differs.'
Need ($null -eq $cfg.cold_registry_hive -or [string]$cfg.cold_registry_hive -eq [string]$contract.hive) 'Private registry hive differs from bound configuration.'
$source=Join-Path (Join-Path $boot 'native-wrapper') $wrapperName;$destination=Join-Path $cfg.addins_directory $wrapperName
$plan=[ordered]@{schema=1;action='install-own-bootstrap';bootstrap_scope_sha256=(Hash $configFile);copy_own_native_wrapper_from=$source;copy_own_native_wrapper_to=$destination;addins_ini=$cfg.addins_ini_file;ini_section=$cold.preload_section;ini_encoding=$cold.ini_encoding;ini_value=$wrapperName;startup_protocol=$cold.startup;registry_hive=$contract.hive;registry_view=32;private_registry_roots=$roots;requires_private_roots_absent_in_HKLM_and_HKCU=$true;requires_editor_closed=$true;editor_executable=$cfg.editor_executable;automatic_elevation=$false;vendor_DLL_modified=$false;starts_Pro=$false;commit_requested=[bool]$Commit}
if(-not $Commit){$plan|ConvertTo-Json -Depth 12;return}
Need (@(BoundEditorProcesses $cfg.editor_executable).Count -eq 0) 'Close the explicitly bound editor normally before bridge installation. No process will be killed.'
Regular $cfg.editor_executable;Need ((Hash $cfg.editor_executable) -eq $cfg.editor_sha256) 'Engineering executable no longer matches its derived loader capability.'
Regular $cfg.addins_ini_file
Need ((Hash $cfg.addins_ini_file) -eq $cfg.addins_ini_sha256) 'Addins.ini changed since this explicit preparation; prepare a new plan.'
Need (-not(Test-Path -LiteralPath $destination)) 'An Addins DLL already exists at this private filename; never overwrite another task installation.'
$machine=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine,[Microsoft.Win32.RegistryView]::Registry32)
$user=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,[Microsoft.Win32.RegistryView]::Registry32)
$registry=if($contract.hive -eq 'HKCU'){$user}else{$machine}
$journalDir=Join-Path $boot ('install-journal-'+[Guid]::NewGuid().ToString('N'));$journal=$null
function WriteJournal($value){$text=$value|ConvertTo-Json -Depth 30;[IO.File]::WriteAllText((Join-Path $journalDir 'installation.json'),$text,(New-Object Text.UTF8Encoding($false)))}
try{
 foreach($root in $roots){foreach($base in @($machine,$user)){$key=$base.OpenSubKey($root,$false);try{Need ($null -eq $key) "Private registration already exists: $root; explicitly remove its prior owned installation first."}finally{if($null -ne $key){$key.Dispose()}}}}
 $startup=$user.OpenSubKey($cfg.startup_registry_path,$false);try{$valueName=[string]$cold.startup.value_name;Need ($null -ne $startup -and $startup.GetValueKind($valueName) -eq [Microsoft.Win32.RegistryValueKind]::DWord) 'Configured original startup DWORD is unavailable.';Need (@($cold.startup.accepted_values) -contains [int]$startup.GetValue($valueName)) 'Current startup state differs from the configured loader protocol.'}finally{if($null -ne $startup){$startup.Dispose()}}
 $before=[IO.File]::ReadAllBytes($cfg.addins_ini_file)
 $ini=Add-McgsColdPreloadEntry $before $wrapperName $cold
 [byte[]]$after=$ini.bytes
 New-Item -ItemType Directory -Path $journalDir|Out-Null
 [IO.File]::WriteAllBytes((Join-Path $journalDir 'Addins.ini.before'),$before)
 [IO.File]::WriteAllBytes((Join-Path $journalDir 'Addins.ini.after'),$after)
 $journal=[ordered]@{schema=1;state='prepared_before_any_install_write';transaction_id=$contract.transaction_id;bootstrap_scope_sha256=(Hash $configFile);roots_absent_before=$roots;registry_hive=$contract.hive;expected_entries=$contract.expected_entries;wrapper_destination=$destination;wrapper_sha256=(Hash $source);ini_file=$cfg.addins_ini_file;ini_before_sha256=(Hash (Join-Path $journalDir 'Addins.ini.before'));ini_after_sha256=(Hash (Join-Path $journalDir 'Addins.ini.after'));no_vendor_DLL_modified=$true;host_started=$false;utc=[DateTime]::UtcNow.ToString('o')}
 WriteJournal $journal
 Need (@(BoundEditorProcesses $cfg.editor_executable).Count -eq 0) 'The bound editor started during installation preparation; preserve the journal and stop.'
 [IO.File]::Copy($source,$destination,$false)
 [IO.File]::WriteAllBytes($cfg.addins_ini_file,$after)
 # Own marker first, then only exact REG_SZ values from the prepared contract.
 foreach($root in $roots){$key=$registry.CreateSubKey($root);try{Need ($key.GetValueNames().Length -eq 0 -and $key.GetSubKeyNames().Length -eq 0) 'A private root appeared after preflight; refuse ownership takeover.';$key.SetValue('CodexBridgeTransactionId',[string]$contract.transaction_id,[Microsoft.Win32.RegistryValueKind]::String);$key.Flush()}finally{$key.Dispose()}}
 foreach($entry in $contract.expected_entries){Need (@($roots|Where-Object{$entry.key -ceq $_ -or $entry.key.StartsWith($_+'\',[StringComparison]::Ordinal)}).Count -eq 1) 'Registration entry escapes its private roots.';$key=$registry.CreateSubKey($entry.key);try{foreach($v in $entry['values'].GetEnumerator()){$key.SetValue($v.Key,[string]$v.Value,[Microsoft.Win32.RegistryValueKind]::String)};$key.Flush()}finally{$key.Dispose()}}
 foreach($entry in $contract.expected_entries){$key=$registry.OpenSubKey($entry.key,$false);try{foreach($v in $entry['values'].GetEnumerator()){Need ($key.GetValueKind($v.Key) -eq [Microsoft.Win32.RegistryValueKind]::String -and [string]$key.GetValue($v.Key) -ceq [string]$v.Value) 'Own private registration readback differs.'}}finally{$key.Dispose()}}
 Need ((Hash $destination) -eq $journal.wrapper_sha256 -and (Hash $cfg.addins_ini_file) -eq $journal.ini_after_sha256) 'Own deployment readback differs.'
 $journal.state='installed_not_started';WriteJournal $journal;$journal|ConvertTo-Json -Depth 30
}catch{
 if($null -ne $journal){$journal.state='partial_or_failed_no_automatic_rollback';$journal.error=$_.Exception.Message;WriteJournal $journal}
 throw
}finally{$machine.Dispose();$user.Dispose()}
