"""Prepare a native engineering program or render its independent comparison."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'assets/pro-native-bridge/client'))

from page_plan import compile_design, normalize_receipts, record_viewports
from page_readback_report import render_review


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, content):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(content)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    compile_command = commands.add_parser('compile')
    compile_command.add_argument('--design', required=True)
    compile_command.add_argument('--snapshot', required=True)
    compile_command.add_argument('--program', required=True, type=Path)
    compile_command.add_argument('--review', required=True, type=Path)
    capture = commands.add_parser('snapshot')
    capture.add_argument('--receipts', required=True, nargs='+')
    capture.add_argument('--viewport')
    capture.add_argument('--out', required=True, type=Path)
    report = commands.add_parser('report')
    report.add_argument('--review', required=True)
    report.add_argument('--snapshot')
    report.add_argument('--receipts', nargs='+', default=[])
    report.add_argument('--evidence')
    report.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'snapshot':
        snapshot = normalize_receipts(read(path) for path in args.receipts)
        if args.viewport:
            record_viewports(snapshot, read(args.viewport))
        write(args.out, encoded(snapshot))
    elif args.command == 'compile':
        if args.program.resolve() == args.review.resolve() or args.program.exists() or args.review.exists():
            raise ValueError('Choose distinct new paths for program and review')
        program, review = compile_design(read(args.design), read(args.snapshot))
        if program['steps']:
            write(args.program, encoded(program))
        write(args.review, encoded(review))
        print(encoded({'actions': len(review['actions']), 'program_written': bool(program['steps']),
                       'native_execution_performed': False}))
    else:
        write(args.out, render_review(read(args.review), read(args.snapshot) if args.snapshot else None,
                                      [read(path) for path in args.receipts],
                                      read(args.evidence) if args.evidence else None))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
