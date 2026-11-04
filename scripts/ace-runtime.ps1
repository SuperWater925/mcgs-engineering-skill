# Shared Windows PowerShell 7 / ACE runtime for McgsStu and McgsPro.
if($PSVersionTable.PSVersion.Major -lt 7){throw 'PowerShell 7 or newer is required for MCGS.'}
if(-not $IsWindows){throw 'The MCGS ACE runtime requires Windows.'}
function Get-McgsAceProviders {
 $items=[Collections.Generic.List[string]]::new()
 $reader=[Data.OleDb.OleDbEnumerator]::GetRootEnumerator()
 try{while($reader.Read()){if([string]$reader['SOURCES_NAME'] -match '^Microsoft\.ACE\.OLEDB\.(12|16)\.0$'){$items.Add([string]$reader['SOURCES_NAME'])}}}finally{$reader.Dispose()}
 return ,@($items.ToArray())
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
