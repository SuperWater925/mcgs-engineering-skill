"""Report a loadable ACE worker independently of frontend/process bitness."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess


def offline_status(powershell=None):
    if os.name != 'nt':
        return {'offline_ready': False, 'reason': 'ACE database editing requires Windows'}
    worker = powershell or os.environ.get('MCGS_PWSH') or shutil.which('pwsh') or shutil.which('powershell')
    if not worker:
        return {'offline_ready': False, 'reason': 'No PowerShell frontend is installed'}
    script = str(Path(__file__).with_name('ace-runtime.ps1')).replace("'", "''")
    code = "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); . '"+script+"'; Get-McgsAceWorker | ConvertTo-Json -Depth 5 -Compress"
    encoded = base64.b64encode(code.encode('utf-16le')).decode('ascii')
    try:
        result = subprocess.run([str(worker), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                                capture_output=True, timeout=45, encoding='utf-8-sig', errors='replace')
        if result.returncode:
            return {'offline_ready': False, 'reason': result.stderr.strip()[-1000:]}
        info = json.loads(result.stdout)
        return {'offline_ready': bool(info.get('ready')), 'ace_worker': info,
                'database_read_verified': False, 'database_write_verified': False}
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {'offline_ready': False, 'reason': str(exc)}
