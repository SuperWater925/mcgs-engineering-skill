# File-only INI transformation shared by installation and focused validation.
function Get-McgsColdIniEncoding([string]$Name) {
 [Text.Encoding]::RegisterProvider([Text.CodePagesEncodingProvider]::Instance)
 if($Name-match'^(?:cp|windows-)?([0-9]+)$'){$code=[int]::Parse($matches[1]);return [Text.Encoding]::GetEncoding($code,[Text.EncoderFallback]::ExceptionFallback,[Text.DecoderFallback]::ExceptionFallback)}
 return [Text.Encoding]::GetEncoding($Name,[Text.EncoderFallback]::ExceptionFallback,[Text.DecoderFallback]::ExceptionFallback)
}
function Add-McgsColdPreloadEntry([byte[]]$Before,[string]$WrapperName,$Runtime) {
 $sectionName=[string]$Runtime.preload_section
 if([string]::IsNullOrEmpty($sectionName)-or$sectionName.IndexOfAny([char[]]"[]`r`n`0")-ge0){throw 'Invalid configured preload section.'}
 $section='['+$sectionName+']';$offset=0;$bom=[byte[]]@()
 $encodingName=[string]$Runtime.ini_encoding
 if($Before.Length-ge3-and$Before[0]-eq239-and$Before[1]-eq187-and$Before[2]-eq191){$encoding=New-Object Text.UTF8Encoding($false,$true);$offset=3;$bom=[byte[]]@(239,187,191)}
 elseif($Before.Length-ge2-and$Before[0]-eq255-and$Before[1]-eq254){$encoding=New-Object Text.UnicodeEncoding($false,$false,$true);$offset=2;$bom=[byte[]]@(255,254)}
 elseif($Before.Length-ge2-and$Before[0]-eq254-and$Before[1]-eq255){$encoding=New-Object Text.UnicodeEncoding($true,$false,$true);$offset=2;$bom=[byte[]]@(254,255)}
 elseif($encodingName-ieq'auto'){$encoding=Get-McgsColdIniEncoding ([string]$Runtime.ini_no_bom_encoding)}
 else{$encoding=Get-McgsColdIniEncoding $encodingName}
 $text=$encoding.GetString($Before,$offset,$Before.Length-$offset)
 [byte[]]$roundtrip=$bom+$encoding.GetBytes($text)
 if([Convert]::ToBase64String($roundtrip)-cne[Convert]::ToBase64String($Before)){throw 'Configured INI encoding does not preserve original bytes.'}
 $lines=New-Object 'Collections.Generic.List[string]';$lines.AddRange([string[]][regex]::Split($text,'(?<=\n)'))
 if($lines.Count-gt0-and$lines[$lines.Count-1].Length-eq0){$lines.RemoveAt($lines.Count-1)}
 $start=-1;$end=$lines.Count;$max=-1
 for($i=0;$i-lt$lines.Count;$i++){if($lines[$i].Trim()-ieq$section){if($start-ne-1){throw 'Duplicate configured preload section.'};$start=$i+1}}
 if($start-ge0){for($i=$start;$i-lt$lines.Count;$i++){if($lines[$i].Trim().StartsWith('[')){$end=$i;break};$match=[regex]::Match($lines[$i],'^\s*([0-9]+)\s*=\s*(.*?)\s*$');if($match.Success){if($match.Groups[2].Value-ieq$WrapperName){throw 'Configured wrapper already has a preload entry.'};$index=[int]::Parse($match.Groups[1].Value);$max=[Math]::Max($max,$index)}}}
 if($max-eq[int]::MaxValue){throw 'INI numeric key space is exhausted.'}
 $newline="`r`n";if($text.Contains("`n")-and-not$text.Contains("`r`n")){$newline="`n"}
 if($start-lt0){if($lines.Count-gt0-and$lines[$lines.Count-1].Length-gt0-and-not$lines[$lines.Count-1].EndsWith("`n")){$lines[$lines.Count-1]+=$newline};$lines.Add($section+$newline);$lines.Add('0='+$WrapperName+$newline)}
 else{if($end-gt0-and-not$lines[$end-1].EndsWith("`n")){$lines[$end-1]+=$newline};$lines.Insert($end,([string]($max+1)+'='+$WrapperName+$newline))}
 [byte[]]$after=$bom+$encoding.GetBytes(($lines-join''))
 return [pscustomobject]@{bytes=$after;encoding=$encoding.WebName;section=$sectionName}
}
