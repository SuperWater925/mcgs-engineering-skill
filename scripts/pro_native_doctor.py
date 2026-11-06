"""Read-only Pro online preparation preflight; no ACE, COM registration or host calls.

Passing this preflight means the supplied file target and build prerequisites
can be used for preparation. Connection permissions and business ABI matching
remain explicitly unevaluated.
"""
import argparse
import hashlib
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def locator_dependency_check():
    """Check the decoder contract without opening or calling the editor."""
    try:
        import capstone
        decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        decoder.detail = True
        instructions = list(decoder.disasm(bytes.fromhex('e800000000c3'), 0x1000))
        if len(instructions) != 2 or instructions[0].mnemonic != 'call':
            raise ValueError('x86 instruction decoding contract differs')
        if instructions[0].imm_offset != 1 or instructions[0].imm_size != 4:
            raise ValueError('Relative-call operand boundaries are unavailable')
        return {'status': 'passed', 'package': 'capstone',
                'version': importlib.metadata.version('capstone'),
                'x86_instruction_boundaries_verified': True,
                'target_Pro_called': False}
    except (ImportError, OSError, ValueError, AttributeError) as error:
        return {'status': 'failed', 'package': 'capstone',
                'reason': type(error).__name__ + ': ' + str(error),
                'prepare': 'Install assets/pro-native-bridge/abi-adapter/requirements.txt with the same Python executable used by run.ps1. Offline editing does not require this package.'}


def command_check(executable, arguments, version=False):
    if not executable or not Path(executable).is_file():
        return {'status': 'failed', 'reason': 'Executable is missing', 'executable': executable}
    try:
        process = subprocess.run([str(executable), *arguments], capture_output=True,
                                 text=True, encoding='utf-8', errors='replace', timeout=10)
        if process.returncode:
            return {'status': 'failed', 'reason': 'Executable probe returned nonzero',
                    'executable': str(executable), 'returncode': process.returncode}
        result = {'status': 'passed', 'executable': str(executable), 'execution_verified': True}
        if version:
            text = process.stdout.strip()
            match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:[-+][A-Za-z0-9.-]+)?', text)
            if not match or int(match.group(1)) < 7:
                return {'status': 'failed', 'reason': 'PowerShell 7 or newer is required',
                        'executable': str(executable), 'observed_version': text[:128]}
            result['version'] = text
        return result
    except (OSError, subprocess.SubprocessError) as error:
        return {'status': 'failed', 'executable': str(executable),
                'reason': type(error).__name__ + ': ' + str(error)}


def editor_check(editor, install):
    if not editor:
        return {'status': 'not_selected', 'reason': 'Supply --install-root or --editor-executable'}
    image = Path(editor)
    if not image.is_absolute():
        return {'status': 'failed', 'reason': 'The selected executable path must be absolute'}
    image = image.resolve()
    if install is not None and not image.is_relative_to(install):
        return {'status': 'failed', 'reason': 'Selected executable is outside the explicit install root'}
    helper = Path(__file__).resolve().parents[1] / 'assets/pro-native-bridge/bootstrap/pe_image.py'
    try:
        spec = importlib.util.spec_from_file_location('mcgs_preflight_pe_image', helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        identity = module.pe32_identity(image)
        return {'status': 'passed', 'executable': str(image), 'read_verified': True,
                'identity': identity, 'author_binary_hash_admission': False}
    except (OSError, ValueError, ImportError, AttributeError) as error:
        return {'status': 'failed', 'executable': str(image),
                'reason': type(error).__name__ + ': ' + str(error)}


def preflight(options):
    windows = os.name == 'nt'
    checks = {
        'windows': {'status': 'passed' if windows else 'failed', 'required': True},
        'python': {'status': 'passed' if sys.version_info >= (3, 11) else 'failed',
                   'executable': sys.executable, 'version': list(sys.version_info[:3]),
                   'execution_verified': True, 'minimum': '3.11'},
    }
    checks['native_function_locator'] = locator_dependency_check()
    powershell = options.powershell_executable or os.environ.get('MCGS_PWSH') or shutil.which('pwsh')
    csc = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
    if windows:
        checks['powershell'] = command_check(powershell, ['-NoProfile', '-NonInteractive', '-Command',
            '[Console]::Out.Write($PSVersionTable.PSVersion.ToString())'], version=True)
        bundle = getattr(options, 'bundle_root', None) or os.environ.get('MCGS_BUNDLE_ROOT')
        if bundle is None:
            candidate = Path(__file__).resolve().parents[2]
            if (candidate / 'bundle.json').is_file():
                bundle = str(candidate)
        if bundle:
            try:
                root = Path(bundle).resolve()
                metadata = json.loads((root / 'bundle.json').read_text(encoding='utf-8-sig'))
                listing = json.loads((root / 'bundle-files.json').read_text(encoding='utf-8-sig'))
                indexed = {row['file']: row for row in listing['files']}
                files = [metadata['business_engine']]
                bridge = root / metadata['bridge_artifacts'] / 'portable-bridge-manifest.json'
                bridge_data = json.loads(bridge.read_text(encoding='utf-8-sig'))
                files += [str(Path(metadata['bridge_artifacts']) / row['file']).replace('\\', '/') for row in bridge_data['artifacts']]
                for relative in files:
                    path = (root / relative).resolve()
                    if not path.is_relative_to(root) or not path.is_file():
                        raise ValueError('Missing packaged own artifact: ' + relative)
                    with path.open('rb') as stream:
                        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                    if digest != indexed[relative]['sha256']:
                        raise ValueError('Packaged own artifact differs: ' + relative)
                checks['x86_framework_csc'] = {'status': 'passed', 'required': False,
                    'reason': 'Verified publisher-precompiled portable artifacts; receiver compilation is unnecessary',
                    'compiled_artifacts_verified': files}
            except (OSError, ValueError, KeyError, TypeError) as error:
                checks['x86_framework_csc'] = {'status': 'failed', 'required': False,
                    'reason': 'Portable distribution artifact check failed: ' + str(error)}
        else:
            checks['x86_framework_csc'] = command_check(str(csc), ['/nologo', '/help'])
    else:
        checks['powershell'] = {'status': 'not_evaluated', 'reason': 'Windows is required'}
        checks['x86_framework_csc'] = {'status': 'not_evaluated', 'reason': 'Windows is required'}

    install = None
    if options.install_root:
        candidate = Path(options.install_root)
        if not candidate.is_absolute() or not candidate.is_dir():
            checks['install_root'] = {'status': 'failed', 'reason': 'Supply an existing absolute install root'}
        else:
            install = candidate.resolve()
            checks['install_root'] = {'status': 'passed', 'path': str(install)}
    else:
        checks['install_root'] = {'status': 'not_selected', 'reason': 'Supply --install-root for preparation'}
    editor = options.editor_executable or (str(install / 'Program/McgsSetPro.exe') if install else None)
    checks['editor'] = editor_check(editor, install)
    ready = all(row['status'] == 'passed' for row in checks.values())
    failures = [name for name, row in checks.items() if row['status'] == 'failed']
    missing = [name for name, row in checks.items() if row['status'] == 'not_selected']
    report = {
        'schema': 1, 'mode': 'online_preparation_preflight',
        'status': 'preparation_prerequisites_passed' if ready else 'not_ready_to_prepare',
        'ready_to_prepare': ready, 'online_ready': False, 'ready_to_connect': None,
        'business_compatibility': 'not_evaluated', 'connection_verified': False,
        'checks': checks, 'failed_checks': failures, 'missing_inputs': missing,
        'permissions': {'target_process_access': 'not_evaluated',
                        'COM_registration': 'not_evaluated', 'task_output_write': 'not_evaluated'},
        'ACE_required_for_this_preflight': False,
        'native_function_location': 'derived_from_selected_program_during_binding',
        'reference_function_RVAs_used_without_resolution': False,
        'Pro_started_or_called': False, 'COM_registered': False, 'project_accessed_or_written': False,
        'meaning': 'ready_to_prepare covers the selected file and build prerequisites only; '
                   'target-process/COM/output permissions, connection, and actual business ABI remain unverified',
    }
    return report, 0 if ready else (1 if failures else 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', help='Actual installation root; default image is Program/McgsSetPro.exe below it')
    parser.add_argument('--editor-executable', help='Explicit actual PE32/I386 Pro image; no release/hash whitelist')
    parser.add_argument('--powershell-executable', help='Actual PowerShell 7 executable; otherwise MCGS_PWSH/PATH')
    parser.add_argument('--bundle-root', help='Complete bundle with publisher-precompiled engine/bridge; Csc is then unnecessary')
    options = parser.parse_args()
    report, code = preflight(options)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
