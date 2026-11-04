param([string]$Workdir)
$ErrorActionPreference = 'Stop'
$taskArgs = @()
if ($env:MCGS_PYTHON) {
    $taskExecutable = $env:MCGS_PYTHON
} else {
    $taskCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($taskCommand) { $taskExecutable = $taskCommand.Source } else {
        $taskExecutable = (Get-Command py -ErrorAction Stop).Source
        $taskArgs = @('-3')
    }
}
if (-not $Workdir) { $Workdir = Join-Path ([IO.Path]::GetTempPath()) ('mcgs-setup-' + [Guid]::NewGuid().ToString('N')) }
[void](New-Item -ItemType Directory -Path $Workdir -Force)
& $taskExecutable @taskArgs (Join-Path $PSScriptRoot 'scripts/mcgs_file.py') doctor --workdir $Workdir
if ($LASTEXITCODE -ne 0) { throw 'Environment check failed. Read the diagnostic output.' }
Write-Host 'Ready: direct MCP file creation/editing; no pip installation required.'
