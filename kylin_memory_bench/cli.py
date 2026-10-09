"""Public one-command dataset, run, scoring, comparison and integrity workflow."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .adapters import validate_config
from .dataset import generate
from .episodes import generate_episodes
from .evidence import environment, verify_manifest, verify_run, write_json
from .model import digest, parse_json, validate_dataset
from .reporting import render_report
from .runner import run_benchmark
from .scoring import score_run


def load(path):
    return parse_json(Path(path).read_text(encoding='utf8'))


def parser():
    p = argparse.ArgumentParser(prog='kmb', description='openKylin agent long-term memory evidence benchmark')
    p.add_argument('--version', action='version', version=__version__)
    commands = p.add_subparsers(dest='command', required=True)
    gen = commands.add_parser('generate', help='generate a frozen six-dimensional dataset')
    gen.add_argument('--seed', type=int, default=42)
    gen.add_argument('--per-dimension', type=int, default=4)
    gen.add_argument('--out', type=Path, required=True)
    episodes = commands.add_parser('generate-episodes', help='generate matched source-availability memory episodes')
    episodes.add_argument('--seed', type=int, default=20261009)
    episodes.add_argument('--split', choices=['development', 'test'], default='test')
    episodes.add_argument('--per-dimension', type=int, default=4)
    episodes.add_argument('--interference-sessions', type=int, default=4)
    episodes.add_argument('--out', type=Path, required=True)
    val = commands.add_parser('validate', help='validate a dataset contract')
    val.add_argument('dataset', type=Path)
    run = commands.add_parser('run', help='run one or multiple native agents with isolated case memory')
    run.add_argument('--dataset', type=Path, required=True)
    run.add_argument('--config', type=Path, required=True)
    run.add_argument('--out', type=Path, required=True)
    run.add_argument('--repeat', type=int, default=1)
    score = commands.add_parser('score', help='recompute a score from verified immutable evidence')
    score.add_argument('run', type=Path)
    score.add_argument('--out', type=Path)
    compare = commands.add_parser('compare', help='create JSON/CSV/HTML and six-dimensional radar')
    compare.add_argument('runs', type=Path, nargs='+')
    compare.add_argument('--out', type=Path, required=True)
    verify = commands.add_parser('verify', help='check all file hashes and sizes')
    verify.add_argument('run', type=Path)
    doctor = commands.add_parser('doctor', help='record OS identity and native agent availability')
    doctor.add_argument('--require-openkylin', action='store_true')
    doctor.add_argument('--out', type=Path)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command in ('generate', 'generate-episodes'):
            data = (generate(args.seed, args.per_dimension) if args.command == 'generate' else
                    generate_episodes(args.seed, args.split, args.per_dimension, args.interference_sessions))
            write_json(args.out, data)
            result = {'dataset': str(args.out), 'sha256': digest(data), 'cases': len(data['cases'])}
        elif args.command == 'validate':
            data = load(args.dataset); validate_dataset(data)
            result = {'ok': True, 'sha256': digest(data), 'cases': len(data['cases'])}
        elif args.command == 'run':
            if not 1 <= args.repeat <= 100:
                raise ValueError('repeat must be between 1 and 100')
            data = load(args.dataset); validate_dataset(data)
            config = load(args.config)
            configs = config.get('agents', [config])
            if not configs or len({c['name'] for c in configs}) != len(configs):
                raise ValueError('agent list must be non-empty with unique names')
            for c in configs:
                validate_config(c)
            args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
            paths = []
            for c in configs:
                for repeat in range(args.repeat):
                    path = args.out / c['name'] / f'repeat-{repeat+1:03d}'
                    run_benchmark(data, c, path, progress=lambda e: print(json.dumps(e), file=sys.stderr, flush=True))
                    paths.append(str(path))
            result = {'runs': paths}
        elif args.command == 'score':
            check = verify_run(args.run)
            if not check['ok']:
                raise ValueError('evidence integrity failed: ' + json.dumps(check['errors']))
            result = score_run(load(args.run / 'dataset.json'), load(args.run / 'run.json'))
            if args.out:
                write_json(args.out, result)
        elif args.command == 'compare':
            scores = []
            for path in args.runs:
                if path.is_dir():
                    if not verify_run(path)['ok']:
                        raise ValueError('evidence integrity failed for ' + str(path))
                    scores.append(score_run(load(path / 'dataset.json'), load(path / 'run.json')))
                else:
                    raise ValueError('compare accepts verified run directories, not loose score files')
            result = render_report(scores, args.out)
        elif args.command == 'verify':
            result = verify_run(args.run) if (args.run / 'run.json').exists() else verify_manifest(args.run)
        else:
            result = {'tool_version': __version__, 'environment': environment(),
                      'agents': {n: bool(shutil.which(n)) for n in ('openclaw', 'hermes')},
                      'dpkg_deb': bool(shutil.which('dpkg-deb'))}
            if args.out:
                write_json(args.out, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == 'verify' and not result['ok']:
            return 2
        if args.command == 'doctor' and args.require_openkylin and not result['environment']['openkylin']:
            return 2
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print('kmb: ' + str(exc), file=sys.stderr)
        return 2
