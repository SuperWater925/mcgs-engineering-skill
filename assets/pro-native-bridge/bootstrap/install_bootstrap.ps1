param([Parameter(Mandatory=$true)][string]$PreparedRoot,[switch]$Commit)
# Default: print the exact installation plan. -Commit is a separate, explicit
# future deployment command; neither prepare nor build invokes this script.
$ErrorActionPreference='Stop'
$boot=(Resolve-Path -LiteralPath $PreparedRoot).Path
function Hash([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function Need([bool]$v,[string]$m){if(-not $v){throw $m}}
function Regular([string]$p){Need (Test-Path -LiteralPath $p -PathType Leaf) "Missing input: $p";for($d=Get-Item -LiteralPath $p;$null -ne $d;$d=$(if($d -is [IO.FileInfo]){$d.Directory}else{$d.Parent})){Need (($d.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) "Reparse input: $p"}}
$configFile=Join-Path $boot 'McgsInternalBridge.bridge.json';Regular $configFile
$cfg=Get-Content -LiteralPath $configFile -Raw -Encoding UTF8|ConvertFrom-Json
$mf=Get-Content -LiteralPath (Join-Path $boot 'build-manifest.json') -Raw -Encoding UTF8|ConvertFrom-Json
Need ($mf.bootstrap_scope_sha256 -eq (Hash $configFile)) 'Bound configuration changed.'
Need ([IO.Path]::GetFullPath($cfg.bootstrap_root) -ieq $boot) 'Prepared bootstrap directory changed.'
foreach($r in $mf.files){$file=Join-Path $boot $r.relative_path;Regular $file;Need ((Hash $file) -eq $r.sha256) "Built file changed: $file"}
$contract=Get-Content -LiteralPath (Join-Path $boot 'prepared-registration-contract.json') -Raw -Encoding UTF8|ConvertFrom-Json
Need ($contract.state -eq 'prepared_not_registered' -and $contract.bootstrap_scope_sha256 -eq (Hash $configFile)) 'Registration contract changed.'
$roots=@('Software\Classes\CLSID\{52119C44-5875-4DA6-9F72-E97D2E2182B4}','Software\Classes\McgsInternalBridge.AddInObj','Software\Classes\TypeLib\{4D2519E0-CC21-4F82-A19C-1AF9801C64E1}')
Need (($contract.roots -join '|') -ceq ($roots -join '|')) 'Private registry scope differs.'
$source=Join-Path $boot 'native-wrapper\McgsInternalLoader.dll';$destination=Join-Path $cfg.addins_directory 'McgsInternalLoader.dll'
$plan=[ordered]@{schema=1;action='install-own-bootstrap';bootstrap_scope_sha256=(Hash $configFile);copy_own_native_wrapper_from=$source;copy_own_native_wrapper_to=$destination;addins_ini=$cfg.addins_ini_file;ini_section='preload section named in loader-capability.json';ini_value='McgsInternalLoader.dll';registry_hive='HKLM';registry_view=32;private_registry_roots=$roots;requires_private_roots_absent_in_HKLM_and_HKCU=$true;requires_editor_closed=$true;automatic_elevation=$false;vendor_DLL_modified=$false;starts_Pro=$false;commit_requested=[bool]$Commit}
if(-not $Commit){$plan|ConvertTo-Json -Depth 12;return}
Need ([Diagnostics.Process]::GetProcessesByName('McgsSetPro').Length -eq 0) 'Close Pro normally before bridge installation. No process will be killed.'
Regular $cfg.editor_executable;Need ((Hash $cfg.editor_executable) -eq $cfg.editor_sha256) 'Engineering executable no longer matches its derived loader capability.'
Regular $cfg.addins_ini_file
Need ((Hash $cfg.addins_ini_file) -eq $cfg.addins_ini_sha256) 'Addins.ini changed since this explicit preparation; prepare a new plan.'
Need (-not(Test-Path -LiteralPath $destination)) 'An Addins DLL already exists at this private filename; never overwrite another task installation.'
for($d=Get-Item -LiteralPath $cfg.addins_directory;$null -ne $d;$d=$d.Parent){Need (($d.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'Addins directory has a reparse ancestor.'}
$machine=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine,[Microsoft.Win32.RegistryView]::Registry32)
$user=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,[Microsoft.Win32.RegistryView]::Registry32)
$journalDir=Join-Path $boot ('install-journal-'+[Guid]::NewGuid().ToString('N'));$journal=$null
function WriteJournal($value){$text=$value|ConvertTo-Json -Depth 30;[IO.File]::WriteAllText((Join-Path $journalDir 'installation.json'),$text,(New-Object Text.UTF8Encoding($false)))}
try{
 foreach($root in $roots){foreach($base in @($machine,$user)){$key=$base.OpenSubKey($root,$false);try{Need ($null -eq $key) "Private registration already exists: $root; explicitly remove its prior owned installation first."}finally{if($null -ne $key){$key.Dispose()}}}}
 $startup=$user.OpenSubKey($cfg.startup_registry_path,$false);try{Need ($null -ne $startup -and $startup.GetValueKind('Count') -eq [Microsoft.Win32.RegistryValueKind]::DWord) 'Explicit original Startup Count DWORD is unavailable.';Need (@(0,1) -contains [int]$startup.GetValue('Count')) 'Unknown original startup state.'}finally{if($null -ne $startup){$startup.Dispose()}}
 $before=[IO.File]::ReadAllBytes($cfg.addins_ini_file)
 $offset=0;$bom=[byte[]]@();$encoding=[Text.Encoding]::GetEncoding(936,[Text.EncoderFallback]::ExceptionFallback,[Text.DecoderFallback]::ExceptionFallback)
 if($before.Length -ge 3 -and $before[0] -eq 239 -and $before[1] -eq 187 -and $before[2] -eq 191){$encoding=New-Object Text.UTF8Encoding($false,$true);$offset=3;$bom=[byte[]]@(239,187,191)}
 elseif($before.Length -ge 2 -and $before[0] -eq 255 -and $before[1] -eq 254){$encoding=New-Object Text.UnicodeEncoding($false,$false,$true);$offset=2;$bom=[byte[]]@(255,254)}
 $text=$encoding.GetString($before,$offset,$before.Length-$offset)
 $section='['+[string]([char]0x9884)+[string]([char]0x88C5)+[string]([char]0x8F7D)+[string]([char]0x6784)+[string]([char]0x4EF6)+']'
 $lines=New-Object 'Collections.Generic.List[string]';$lines.AddRange([string[]][regex]::Split($text,'(?<=\n)'))
 $start=-1;$end=$lines.Count;$max=-1
 for($i=0;$i -lt $lines.Count;$i++){if($lines[$i].Trim() -ceq $section){Need ($start -eq -1) 'Duplicate original preload section.';$start=$i+1}}
 if($start -ge 0){for($i=$start;$i -lt $lines.Count;$i++){if($lines[$i].Trim().StartsWith('[')){$end=$i;break};$match=[regex]::Match($lines[$i],'^\s*([0-9]+)\s*=\s*(.*?)\s*$');if($match.Success){Need ($match.Groups[2].Value -ine 'McgsInternalLoader.dll') 'Existing preload bridge entry belongs to an earlier task.';$max=[Math]::Max($max,[int]$match.Groups[1].Value)}}}
 Need ($max -lt 65535) 'Original preload numeric namespace is exhausted.'
 $newline="`r`n";if($text.Contains("`n") -and -not $text.Contains("`r`n")){$newline="`n"}
 if($start -lt 0){if($lines.Count -gt 0 -and $lines[$lines.Count-1].Length -gt 0 -and -not $lines[$lines.Count-1].EndsWith("`n")){$lines[$lines.Count-1]+=$newline};$lines.Add($section+$newline);$lines.Add('0=McgsInternalLoader.dll'+$newline)}
 else{if($end -gt 0 -and -not $lines[$end-1].EndsWith("`n")){$lines[$end-1]+=$newline};$lines.Insert($end,([string]($max+1)+'=McgsInternalLoader.dll'+$newline))}
 $afterText=$lines -join '';[byte[]]$after=$bom+$encoding.GetBytes($afterText)
 New-Item -ItemType Directory -Path $journalDir|Out-Null
 [IO.File]::WriteAllBytes((Join-Path $journalDir 'Addins.ini.before'),$before)
 [IO.File]::WriteAllBytes((Join-Path $journalDir 'Addins.ini.after'),$after)
 $journal=[ordered]@{schema=1;state='prepared_before_any_install_write';transaction_id=$contract.transaction_id;bootstrap_scope_sha256=(Hash $configFile);roots_absent_before=$roots;expected_entries=$contract.expected_entries;wrapper_destination=$destination;wrapper_sha256=(Hash $source);ini_file=$cfg.addins_ini_file;ini_before_sha256=(Hash (Join-Path $journalDir 'Addins.ini.before'));ini_after_sha256=(Hash (Join-Path $journalDir 'Addins.ini.after'));no_vendor_DLL_modified=$true;host_started=$false;utc=[DateTime]::UtcNow.ToString('o')}
 WriteJournal $journal
 [IO.File]::Copy($source,$destination,$false)
 [IO.File]::WriteAllBytes($cfg.addins_ini_file,$after)
 # Own marker first, then only exact REG_SZ values from the prepared contract.
 foreach($root in $roots){$key=$machine.CreateSubKey($root);try{Need ($key.GetValueNames().Length -eq 0 -and $key.GetSubKeyNames().Length -eq 0) 'A private root appeared after preflight; refuse ownership takeover.';$key.SetValue('CodexBridgeTransactionId',[string]$contract.transaction_id,[Microsoft.Win32.RegistryValueKind]::String);$key.Flush()}finally{$key.Dispose()}}
 foreach($entry in $contract.expected_entries){Need (@($roots|Where-Object{$entry.key -ceq $_ -or $entry.key.StartsWith($_+'\',[StringComparison]::Ordinal)}).Count -eq 1) 'Registration entry escapes its private roots.';$key=$machine.CreateSubKey($entry.key);try{foreach($v in $entry.values.PSObject.Properties){$key.SetValue($v.Name,[string]$v.Value,[Microsoft.Win32.RegistryValueKind]::String)};$key.Flush()}finally{$key.Dispose()}}
 foreach($entry in $contract.expected_entries){$key=$machine.OpenSubKey($entry.key,$false);try{foreach($v in $entry.values.PSObject.Properties){Need ($key.GetValueKind($v.Name) -eq [Microsoft.Win32.RegistryValueKind]::String -and [string]$key.GetValue($v.Name) -ceq [string]$v.Value) 'Own private registration readback differs.'}}finally{$key.Dispose()}}
 Need ((Hash $destination) -eq $journal.wrapper_sha256 -and (Hash $cfg.addins_ini_file) -eq $journal.ini_after_sha256) 'Own deployment readback differs.'
 $journal.state='installed_not_started';WriteJournal $journal;$journal|ConvertTo-Json -Depth 30
}catch{
 if($null -ne $journal){$journal.state='partial_or_failed_no_automatic_rollback';$journal.error=$_.Exception.Message;WriteJournal $journal}
 throw
}finally{$machine.Dispose();$user.Dispose()}
