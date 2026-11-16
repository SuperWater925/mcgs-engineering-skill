# Shared ACE worker runtime. The editing frontend may be x64 while ACE is x86.
if([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT){throw 'The MCGS ACE runtime requires Windows.'}
function Get-McgsAceProviders {
 $items=[Collections.Generic.List[string]]::new()
 $reader=[Data.OleDb.OleDbEnumerator]::GetRootEnumerator()
 try{while($reader.Read()){
  $name=[string]$reader['SOURCES_NAME'];if($name -notmatch '^Microsoft\.ACE\.OLEDB\.(12|16)\.0$'){continue}
  $instance=$null
  try{$instance=[Activator]::CreateInstance([Type]::GetTypeFromProgID($name,$true));$items.Add($name)}catch{}
  finally{if($null -ne $instance -and [Runtime.InteropServices.Marshal]::IsComObject($instance)){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($instance)}}
 }}finally{$reader.Dispose()}
 return ,@($items.ToArray())
}
function Get-McgsAceWorker([string]$Provider='auto') {
 $current=(Get-Process -Id $PID).Path
 try{$providers=Get-McgsAceProviders;if($Provider -ne 'auto'){$providers=@($providers|Where-Object {$_ -eq $Provider})}}catch{$providers=@()}
 if($providers.Count){return [pscustomobject]@{ready=$true;path=$current;process_bits=([IntPtr]::Size*8);providers=$providers}}
 $candidates=[Collections.Generic.List[string]]::new()
 foreach($configured in @($env:MCGS_ACE_PWSH,$env:MCGS_PWSH_X86,$env:MCGS_PWSH_X64,$env:MCGS_PWSH)){
  if($configured){$candidates.Add($configured)}
 }
 foreach($root in @(${env:ProgramFiles(x86)},$env:ProgramW6432,$env:ProgramFiles)){
  if($root){$candidates.Add((Join-Path $root 'PowerShell/7/pwsh.exe'))}
 }
 foreach($directory in @('SysWOW64','System32','Sysnative')){
  if($env:WINDIR){$candidates.Add((Join-Path $env:WINDIR ($directory+'/WindowsPowerShell/v1.0/powershell.exe')))}
 }
 $probe=@'
$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);$p=@();$r=[Data.OleDb.OleDbEnumerator]::GetRootEnumerator()
try{while($r.Read()){$n=[string]$r['SOURCES_NAME'];if($n -notmatch '^Microsoft\.ACE\.OLEDB\.(12|16)\.0$'){continue};$o=$null;try{$o=[Activator]::CreateInstance([Type]::GetTypeFromProgID($n,$true));$p+=$n}catch{}finally{if($null -ne $o -and [Runtime.InteropServices.Marshal]::IsComObject($o)){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($o)}}}}finally{$r.Dispose()}
@{process_bits=([IntPtr]::Size*8);providers=@($p)}|ConvertTo-Json -Compress
'@
 $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($probe))
 foreach($candidate in @($candidates|Select-Object -Unique)){
  if($candidate -ieq $current -or -not(Test-Path -LiteralPath $candidate -PathType Leaf)){continue}
  try{
   $raw=& $candidate -NoProfile -NonInteractive -EncodedCommand $encoded 2>$null
   if($LASTEXITCODE -ne 0){continue};$result=($raw|Out-String|ConvertFrom-Json)
   $available=@($result.providers|Where-Object {$Provider -eq 'auto' -or $_ -eq $Provider})
   if($available.Count){return [pscustomobject]@{ready=$true;path=$candidate;process_bits=$result.process_bits;providers=$available}}
  }catch{}
 }
 return [pscustomobject]@{ready=$false;path=$null;process_bits=$null;providers=@();reason='No installed worker can load ACE 12/16; install ACE for an available worker architecture.'}
}

# The narrow database worker also runs under Windows PowerShell 5.1 when only
# that architecture has ACE. Keep compatibility here, not in online startup.
function ConvertFrom-McgsJson([string]$Json){
 function Convert-Map($Value){
  if($null -eq $Value){return $null}
  if($Value -is [System.Management.Automation.PSCustomObject]){
   $map=@{};foreach($p in $Value.PSObject.Properties){$map[$p.Name]=Convert-Map $p.Value};return ,$map
  }
  if($Value -is [Array]){return ,@($Value|ForEach-Object {Convert-Map $_})}
  return $Value
 }
 return Convert-Map ($Json|ConvertFrom-Json)
}
function Get-McgsRelativePath([string]$Root,[string]$Path){
 $base=[Uri]::new(([IO.Path]::GetFullPath($Root).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar))
 return [Uri]::UnescapeDataString($base.MakeRelativeUri([Uri]::new([IO.Path]::GetFullPath($Path))).ToString()).Replace('/',[IO.Path]::DirectorySeparatorChar)
}
function New-McgsAceConnectionString([string]$Path,[string]$Mode,[string]$Provider,[switch]$Create){
 $builder=[Data.OleDb.OleDbConnectionStringBuilder]::new()
 $builder['Provider']=$Provider;$builder['Data Source']=$Path
 if(-not $Create){$builder['Persist Security Info']=$false}
 if($Mode){$builder['Mode']=$Mode}
 if($Create){$builder['Jet OLEDB:Engine Type']=5}
 return $builder.ConnectionString
}
function Open-McgsAceConnection([string]$Path,[string]$Mode='Read',[string]$Provider='auto'){
 $candidates=if($Provider -eq 'auto'){@('Microsoft.ACE.OLEDB.16.0','Microsoft.ACE.OLEDB.12.0')}else{@($Provider)}
 foreach($candidate in $candidates){
  $connection=[Data.OleDb.OleDbConnection]::new((New-McgsAceConnectionString $Path $Mode $candidate))
  try{$connection.Open();return ,$connection}catch{$connection.Dispose()}
 }
 throw 'ACE could not open the project. Check provider/process bitness, database format, locks and path; no editor process was closed.'
}

function New-McgsAceCatalog {
 return New-Object -ComObject ADOX.Catalog
}

function New-McgsAceDatabase([string]$Path,[string]$Provider='auto'){
 $destination=[IO.Path]::GetFullPath($Path)
 $parent=[IO.Path]::GetDirectoryName($destination)
 if(-not [IO.Directory]::Exists($parent)){throw 'Database output parent must already exist.'}
 if(Test-Path -LiteralPath $destination){throw 'Database output already exists.'}
 $candidates=if($Provider -eq 'auto'){@('Microsoft.ACE.OLEDB.16.0','Microsoft.ACE.OLEDB.12.0')}else{@($Provider)}
 $failures=[Collections.Generic.List[string]]::new()
 foreach($candidate in $candidates){
  # Each provider gets a private new file; a failed provider never owns the
  # caller's output path. Only a successfully closed catalog is published.
  $temporary=Join-Path $parent ('.mcgs-ace-create-'+[Guid]::NewGuid().ToString('N')+'.mdb')
  if(Test-Path -LiteralPath $temporary){throw 'Private database candidate unexpectedly exists.'}
  $catalog=$null;$active=$null;$created=$false
  try{
   $catalog=New-McgsAceCatalog
   $catalog.Create((New-McgsAceConnectionString $temporary '' $candidate -Create)) | Out-Null
   $active=$catalog.ActiveConnection
   if($null -ne $active){$active.Close()}
   if(-not [IO.File]::Exists($temporary)){throw 'ADOX did not create the requested private candidate.'}
   $created=$true
  }catch{
   $failures.Add($candidate+': '+$_.Exception.Message)
  }finally{
   if($null -ne $active -and [Runtime.InteropServices.Marshal]::IsComObject($active)){
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($active)
   }
   if($null -ne $catalog -and [Runtime.InteropServices.Marshal]::IsComObject($catalog)){
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($catalog)
   }
   if(-not $created -and (Test-Path -LiteralPath $temporary)){
    Remove-Item -LiteralPath $temporary
   }
  }
  if($created){
   # File.Move refuses a concurrently created destination. Do not retry a
   # publication error or remove another actor's destination.
   [IO.File]::Move($temporary,$destination)
   return [pscustomobject]@{Provider=$candidate;Path=$destination}
  }
 }
 throw ('ACE could not create a new database with the requested providers. '+($failures -join '; '))
}
