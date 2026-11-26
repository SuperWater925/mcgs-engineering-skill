"""Compare a built launcher to its bundled Python without network or vendor calls."""
import argparse
import json
from pathlib import Path
import subprocess


def check(root):
    root = Path(root).resolve(strict=True)
    metadata = json.loads((root / 'bundle.json').read_text(encoding='utf-8-sig'))
    launcher = root / 'McgsStart.exe'
    python = root / metadata['python']
    script = root / metadata['skill_directory'] / 'scripts/turnkey.py'
    results = []
    for args, expected in [(['--help'], 0), (['__invalid_launcher_regression_command__'], 2)]:
        direct = subprocess.run([str(python), '-B', '-X', 'utf8', str(script), '--bundle-root', str(root), *args],
                                cwd=root, capture_output=True, timeout=30)
        outer = subprocess.run([str(launcher), *args], cwd=root, capture_output=True, timeout=30)
        if direct.returncode != expected or outer.returncode != direct.returncode:
            raise AssertionError(f'Exit code mismatch: expected={expected}, Python={direct.returncode}, launcher={outer.returncode}')
        if (direct.stdout, direct.stderr) != (outer.stdout, outer.stderr):
            raise AssertionError('Launcher changed or mixed stdout/stderr')
        results.append({'arguments': args, 'exit_code': outer.returncode, 'streams_equal': True})
    return {'passed': True, 'cases': results, 'vendor_software_executed': False, 'network_used': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-root', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.bundle_root), indent=2))
