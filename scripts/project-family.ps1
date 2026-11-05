# Match the same product brand as the Python entry points; release numbers are observations.
$familyContractPath=Join-Path $PSScriptRoot 'native/project_family.json'
$script:McgsFamilyContract=Get-Content -LiteralPath $familyContractPath -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
if($script:McgsFamilyContract.schema -ne 1){throw 'Unsupported shared project-family contract.'}
function Get-McgsProjectFamily([string]$Version){
 $brand=[regex]::Match($Version.TrimStart([char]0xFEFF),$script:McgsFamilyContract.brand_pattern,[Text.RegularExpressions.RegexOptions]::IgnoreCase)
 if(-not $brand.Success){return 'unrecognized'}
 if($brand.Groups[1].Value -ieq 'pro'){return 'Pro'}
 return 'Stu'
}
