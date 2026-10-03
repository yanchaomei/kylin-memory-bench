#!/usr/bin/env python3
"""Build an architecture-independent Debian package with no network installs."""
import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    if not shutil.which('dpkg-deb'):
        parser.error('dpkg-deb is required; build on openKylin or a Debian-compatible Linux host')
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='kmb-deb-') as tmp:
        stage = Path(tmp)
        lib = stage / 'usr/lib/kylin-memory-bench'
        lib.mkdir(parents=True)
        shutil.copytree(ROOT / 'kylin_memory_bench', lib / 'kylin_memory_bench', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copyfile(ROOT / 'kmb', lib / 'kmb')
        (lib / 'kmb').chmod(0o755)
        share = stage / 'usr/share/kylin-memory-bench'
        for name in ('configs', 'data', 'docs'):
            shutil.copytree(ROOT / name, share / name)
        shutil.copyfile(ROOT / 'README.md', share / 'README.md')
        license_dir = stage / 'usr/share/doc/kylin-memory-bench'; license_dir.mkdir(parents=True)
        shutil.copyfile(ROOT / 'LICENSE', license_dir / 'copyright')
        bin_dir = stage / 'usr/bin'; bin_dir.mkdir(parents=True)
        (bin_dir / 'kmb').symlink_to('../lib/kylin-memory-bench/kmb')
        control = stage / 'DEBIAN'; control.mkdir()
        (control / 'control').write_text(
            'Package: kylin-memory-bench\nVersion: 0.1.0\nSection: science\nPriority: optional\n'
            'Architecture: all\nMaintainer: Kylin Memory Bench Contributors\nDepends: python3 (>= 3.10)\n'
            'Description: Evidence-based agent long-term memory benchmark\n'
            ' Six-dimensional dataset, native agent adapters, deterministic scoring\n'
            ' and reproducible HTML/CSV/JSON reports for openKylin.\n')
        target = args.out / 'kylin-memory-bench_0.1.0_all.deb'
        env = dict(os.environ, SOURCE_DATE_EPOCH='1790985600')
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(stage), str(target)], check=True, env=env)
        print(target)


if __name__ == '__main__':
    main()
