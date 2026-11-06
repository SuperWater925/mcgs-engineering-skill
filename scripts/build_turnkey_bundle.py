"""Publisher-only complete bundle assembler. Never runs a vendor installer.

Inputs are explicitly supplied, complete installation media and already built
own engines. Customer projects, installed application trees and Git metadata
are not distribution inputs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def copy_tree(source, target):
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', 'local-artifacts'))


def extract_zip(source, target):
    target.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(source) as archive:
        for item in archive.infolist():
            final = (target / item.filename).resolve()
            if not final.is_relative_to(target.resolve()) or ((item.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError('Non-contained archive entry: ' + item.filename)
        archive.extractall(target)


def rows(root):
    return [{'file': str(path.relative_to(root)).replace('\\', '/'),
             'size': path.stat().st_size, 'sha256': sha(path)}
            for path in sorted(root.rglob('*')) if path.is_file()]


def assemble(args):
    target = args.output.resolve()
    if target.exists():
        raise ValueError('Output must be a fresh directory')
    target.mkdir(parents=True)
    source = Path(__file__).resolve().parents[1]
    copy_tree(source, target / 'skill')
    runtime = target / 'runtime'
    extract_zip(args.python_zip, runtime / 'python')
    extract_zip(args.powershell_zip, runtime / 'pwsh')
    # The embedded distribution isolates sys.path. Keep it portable while adding
    # package scripts/ABI modules without relying on an installed site package.
    pth = next((runtime / 'python').glob('python*._pth'))
    lines = pth.read_text(encoding='utf-8').splitlines()
    lines = [line for line in lines if line.strip() not in ('#import site', 'import site')]
    lines += ['Lib/site-packages', '../../skill/scripts', 'import site']
    pth.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    packages = runtime / 'python/Lib/site-packages'
    packages.mkdir(parents=True)
    # ._pth intentionally isolates an embedded interpreter, including dropping
    # the invoked script's sibling imports. Restore only ordinary script-dir
    # semantics (not cwd/PYTHONPATH/user-site) for all existing skill CLIs.
    (packages / 'sitecustomize.py').write_text(
        'import sys\nfrom pathlib import Path\n'
        'if sys.argv and sys.argv[0] and sys.argv[0] not in ("-c", "-m"):\n'
        '    _mcgs_script = Path(sys.argv[0])\n'
        '    if _mcgs_script.is_file():\n'
        '        sys.path.insert(0, str(_mcgs_script.resolve().parent))\n', encoding='utf-8')
    for wheel in sorted(args.wheels.glob('*.whl')):
        if wheel.name.lower().startswith('rarfile-'):
            continue  # Publisher extraction helper, never a receiver dependency.
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(packages)
    copy_tree(args.business, target / 'engine/business')
    copy_tree(args.bridge, target / 'engine/bridge')
    (target / 'tools').mkdir()
    for exe in args.tools.glob('*.exe'):
        shutil.copy2(exe, target / 'tools' / exe.name)
    shutil.copy2(args.tools / 'McgsStart.exe', target / 'McgsStart.exe')
    products = []
    for family, media, version, label in [
        ('pro', args.pro_media, '3.5.2.12210', 'McgsPro 3.5.2.12210'),
        ('stu', args.stu_media, '3.5.3.9198', 'McgsStu 3.5.3.9198 SP1'),
    ]:
        dest = target / 'vendor' / family / 'media'
        copy_tree(media, dest)
        setup = dest / 'Setup.exe'
        editor_name = 'McgsSetPro.exe' if family == 'pro' else 'McgsSetStu.exe'
        editor = dest / 'Bin' / editor_name
        if not setup.is_file() or not editor.is_file():
            raise ValueError('Incomplete vendor media: ' + family)
        products.append({'family': family, 'label': label, 'version': version,
                         'editor_name': editor_name,
                         'default_install_root': 'C:\\Mcgs' + ('Pro' if family == 'pro' else 'Stu'),
                         'installer': {'file': setup.relative_to(target).as_posix(), 'sha256': sha(setup)},
                         'reference_editor': {'file': editor.relative_to(target).as_posix(), 'sha256': sha(editor)},
                         'version_policy': 'informational_choice_not_admission',
                         'media_manifest': f'vendor/{family}/media-files.json'})
        dump(dest.parent / 'media-files.json', {'schema': 1, 'files': rows(dest),
            'directories': [path.relative_to(dest).as_posix() for path in sorted(dest.rglob('*')) if path.is_dir()]})
    dep = target / 'runtime/installers'
    dep.mkdir()
    shutil.copy2(args.ace_installer, dep / args.ace_installer.name)
    manifest = {
        'schema': 'mcgs-turnkey-bundle/v1', 'release': args.release,
        'skill_directory': 'skill',
        'python': 'runtime/python/python.exe', 'powershell': 'runtime/pwsh/pwsh.exe',
        'bridge_artifacts': 'engine/bridge',
        'business_engine': 'engine/business/McgsEngineering.Portable.dll',
        'choice_helper': 'tools/InstallerChoice.exe',
        'products': products,
        'ace': {'file': 'runtime/installers/' + args.ace_installer.name,
                'sha256': sha(dep / args.ace_installer.name),
                'optional_for': ['pro-offline', 'stu-offline'], 'required_for_pro_online': False},
        'receiver_compilation_required': False,
        'bundle_platform': 'Windows x64',
        'vendor_media_in_git_source': False,
        'vendor_media_distribution': 'separate_complete_bundle_release_asset',
    }
    dump(target / 'bundle.json', manifest)
    shutil.copy2(source / 'references/turnkey-start-zh.md', target / '使用说明.md')
    shutil.copy2(source / 'references/turnkey-third-party.md', target / '第三方许可说明.md')
    # Shell wrappers accept exact structured argument lists; no interpolated
    # PowerShell command strings and no inherited Python installation needed.
    (target / 'McgsRun.cmd').write_text('@echo off\r\nset "MCGS_PYTHON=%~dp0runtime\\python\\python.exe"\r\nset "MCGS_PWSH=%~dp0runtime\\pwsh\\pwsh.exe"\r\n"%MCGS_PWSH%" -NoProfile -File "%~dp0skill\\run.ps1" %*\r\n', encoding='ascii')
    (target / 'McgsSetup.cmd').write_text('@echo off\r\n"%~dp0McgsStart.exe" %*\r\n', encoding='ascii')
    dump(target / 'bundle-files.json', {'schema': 1, 'files': rows(target)})
    if args.stage_only:
        print(json.dumps({'schema': 1, 'status': 'bundle_staged_not_archived', 'bundle_root': str(target),
                          'files': len(rows(target)), 'installers_executed': False}, ensure_ascii=False, indent=2))
        return
    if not args.zip:
        raise ValueError('--zip is required unless --stage-only is used')
    archive_path = args.zip.resolve()
    if archive_path.exists():
        raise ValueError('Archive already exists')
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, 'x', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in sorted(target.rglob('*')):
            archive.write(path, target.name + '/' + path.relative_to(target).as_posix())
    result = {'schema': 1, 'bundle_root': str(target), 'zip': str(archive_path),
              'size': archive_path.stat().st_size, 'sha256': sha(archive_path),
              'files': len(rows(target)), 'installers_executed': False}
    dump(archive_path.with_suffix('.sha256.json'), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('python-zip', 'powershell-zip', 'wheels', 'business', 'bridge', 'tools', 'pro-media', 'stu-media', 'ace-installer', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--zip', type=Path)
    parser.add_argument('--stage-only', action='store_true')
    parser.add_argument('--release', required=True)
    assemble(parser.parse_args())


if __name__ == '__main__':
    main()
