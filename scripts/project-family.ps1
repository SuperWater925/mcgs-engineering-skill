# Match the same product brand as the Python entry points; release numbers are observations.
$familyContractPath=Join-Path $PSScriptRoot 'native/project_family.json'
$script:McgsFamilyContract=Get-Content -LiteralPath $familyContractPath -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
$script:McgsNativeArchiveTool=Join-Path $PSScriptRoot 'native/mcgs_native_zip.py'
if($script:McgsFamilyContract.schema -ne 1){throw 'Unsupported shared project-family contract.'}
function Get-McgsProjectFamily([string]$Version){
 $brand=[regex]::Match($Version.TrimStart([char]0xFEFF),$script:McgsFamilyContract.brand_pattern,[Text.RegularExpressions.RegexOptions]::IgnoreCase)
 if(-not $brand.Success){return 'unrecognized'}
 if($brand.Groups[1].Value -ieq 'pro'){return 'Pro'}
 return 'Stu'
}
function Get-McgsVersionText([byte[]]$Archive){
 # Reuse the byte codec, including zlib EOF/checksum/trailing-data checks.
 # Plain version records do not need a Python process.
 if($Archive.Length -ge 8 -and [Text.Encoding]::ASCII.GetString($Archive,0,8) -eq 'MCGSZIPE'){
  $python=if($env:MCGS_PYTHON){$env:MCGS_PYTHON}else{(Get-Command python -ErrorAction Stop).Source}
  $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$python
  $start.UseShellExecute=$false;$start.CreateNoWindow=$true
  $start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
  foreach($arg in @('-B',$script:McgsNativeArchiveTool,'--unpack-base64')){[void]$start.ArgumentList.Add($arg)}
  $process=[Diagnostics.Process]::Start($start)
  try{
   $process.StandardInput.Write([Convert]::ToBase64String($Archive));$process.StandardInput.Close()
   $output=$process.StandardOutput.ReadToEnd();$errorText=$process.StandardError.ReadToEnd();$process.WaitForExit()
   if($process.ExitCode -ne 0){throw ('Invalid native version archive: '+$errorText.Trim())}
   $Archive=[Convert]::FromBase64String($output.Trim())
  }finally{$process.Dispose()}
 }
 if($Archive.Length%2){throw 'Native version text has an odd UTF-16 byte length.'}
 return [Text.UnicodeEncoding]::new($false,$false,$true).GetString($Archive).TrimEnd([char]0)
}
