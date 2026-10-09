#!/usr/bin/env python3
"""Package only this benchmark's source and verified shareable evidence."""
import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kylin_memory_bench.evidence import sha256, verify_manifest, verify_run
from kylin_memory_bench import __version__


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--runs', type=Path, nargs='*', default=[])
    parser.add_argument('--reports', type=Path, nargs='*', default=[])
    args = parser.parse_args()
    entries = {}
    for name in ('kylin_memory_bench', 'configs', 'data', 'docs', 'tests', 'scripts'):
        for path in (ROOT / name).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                entries['source/' + path.relative_to(ROOT).as_posix()] = path
    for name in ('kmb', 'README.md', 'LICENSE', 'pyproject.toml', '.gitignore'):
        entries['source/' + name] = ROOT / name
    for path in (ROOT / 'dist').glob(f'kylin-memory-bench_{__version__}_*.deb'):
        entries['packages/' + path.name] = path
    for root in args.runs:
        check = verify_run(root)
        if not check['ok']:
            raise ValueError('invalid run: ' + str(root) + ' ' + json.dumps(check['errors']))
        run = json.loads((root / 'run.json').read_text())
        prefix = 'evidence/' + run['environment']['system'] + '/' + run['run_id'] + '/'
        for p in root.rglob('*'):
            if p.is_file():
                entries[prefix + p.relative_to(root).as_posix()] = p
    for root in args.reports:
        if not verify_manifest(root)['ok']:
            raise ValueError('invalid report: ' + str(root))
        for p in root.rglob('*'):
            if p.is_file():
                entries['reports/' + root.name + '/' + p.relative_to(root).as_posix()] = p
    manifest = {'schema': 'kmb.delivery/v1', 'ready_for_submission': False,
                'remaining': ['two real agents with successful model calls on openKylin', '3-5 minute real openKylin desktop recording'],
                'files': [{'path': name, 'bytes': p.stat().st_size, 'sha256': sha256(p.read_bytes())} for name, p in sorted(entries.items())]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        raise FileExistsError('refusing to overwrite a delivery archive')
    with zipfile.ZipFile(args.out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, p in sorted(entries.items()):
            archive.write(p, 'KylinMemoryBench/' + name)
        archive.writestr('KylinMemoryBench/delivery.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(args.out) as archive:
        assert archive.testzip() is None
        for item in manifest['files']:
            assert sha256(archive.read('KylinMemoryBench/' + item['path'])) == item['sha256']
    print(json.dumps({'archive': str(args.out), 'bytes': args.out.stat().st_size,
                      'sha256': sha256(args.out.read_bytes()), 'files': len(entries), 'ready_for_submission': False}, indent=2))


if __name__ == '__main__':
    main()
