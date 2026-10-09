#!/usr/bin/env python3
"""Run independent frozen trials concurrently; only reuse fully verified trials."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
import os
import re
import select
import stat
from pathlib import Path
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kylin_memory_bench.adapters import validate_config
from kylin_memory_bench.evidence import build_manifest, confined_file, sha256, verify_run, write_json
from kylin_memory_bench.model import digest, parse_json, validate_dataset
from kylin_memory_bench.privacy import redact, redact_object
from kylin_memory_bench.runner import run_benchmark

SCHEDULER_SHA256 = sha256(Path(__file__).read_bytes())


def source_fingerprint():
    return digest({p.name: sha256(p.read_bytes()) for p in sorted((ROOT / 'kylin_memory_bench').glob('*.py'))})


def public_configuration(config):
    secrets = {v for k, v in os.environ.items() if re.search('KEY|TOKEN|SECRET|PASSWORD', k) and len(v) >= 8}
    secrets.update(str(v) for k, v in config.get('env', {}).items()
                   if re.search('KEY|TOKEN|SECRET|PASSWORD', k) and len(str(v)) >= 8)
    command = config.get('command', [])
    secrets.update(command[i + 1] for i, arg in enumerate(command[:-1])
                   if arg in ('--api-key', '--token', '--password', '--secret'))
    result = redact_object({k: v for k, v in config.items() if k not in ('credential_home', 'env')}, secrets)
    result['environment_keys'] = sorted(config.get('env', {}))
    return result


def atomic_json(path, obj):
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with controller_file(tmp, 'x') as file:
            file.write(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def controller_file(path, mode):
    flags = {'r': os.O_RDONLY, 'a': os.O_WRONLY | os.O_APPEND | os.O_CREAT,
             'a+': os.O_RDWR | os.O_APPEND | os.O_CREAT,
             'x': os.O_WRONLY | os.O_CREAT | os.O_EXCL}[mode]
    fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
        os.close(fd)
        raise ValueError('controller file must be an owned regular file without links')
    return os.fdopen(fd, mode, encoding='utf8')


def read_credentials(path, expected_names, timeout=60):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISFIFO(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError('credential input must be an owned mode-0600 FIFO')
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        current = os.fstat(fd)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError('credential FIFO changed during opening')
        packet = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not select.select([fd], [], [], max(0, deadline - time.monotonic()))[0]:
                break
            block = os.read(fd, 4096)
            if not block:
                if packet:
                    break
                time.sleep(.02)
                continue
            packet.extend(block)
            if len(packet) > 65536:
                raise ValueError('credential packet exceeds limit')
        if not packet:
            raise ValueError('credential FIFO delivery timed out')
        obj = parse_json(packet.decode('utf8'))
        if not isinstance(obj, dict) or set(obj) != set(expected_names):
            raise ValueError('credential packet environment names differ')
        if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k)
               or not isinstance(v, str) or not v or '\x00' in v for k, v in obj.items()):
            raise ValueError('credential packet is invalid')
        return obj
    finally:
        os.close(fd)
        if path.exists() and not path.is_symlink() and path.lstat().st_ino == info.st_ino:
            path.unlink()


def run_study(data, configs, output, *, repeats=3, parallel=2, python=sys.executable, progress=None):
    validate_dataset(data)
    if not configs or len({c['name'] for c in configs}) != len(configs):
        raise ValueError('study requires unique agent names')
    if type(repeats) is not int or not 1 <= repeats <= 100 or type(parallel) is not int or not 1 <= parallel <= 8:
        raise ValueError('repeats must be 1-100 and parallel must be 1-8')
    for config in configs:
        validate_config(config)
    output = Path(output).absolute()
    if output.is_symlink():
        raise ValueError('study output must not be a symlink')
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.is_symlink():
        raise ValueError('study output must not be a symlink')
    definition = {'dataset_sha256': digest(data), 'configurations': {c['name']: digest(c) for c in configs},
                  'repeats': repeats, 'parallel': parallel, 'source_sha256': source_fingerprint(),
                  'scheduler_sha256': SCHEDULER_SHA256,
                  'policy': 'independent complete trials; no phase splicing or selective retry'}
    controls = {name: confined_file(output, name) for name in
                ('.study.lock', 'study-plan.json', 'events.jsonl', 'study-progress.json', 'study.json')}
    claims = confined_file(output, '.trial-claims')
    claims.mkdir(mode=0o700, exist_ok=True)
    with controller_file(controls['.study.lock'], 'a+') as file:
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('another controller owns this study')
        plan = controls['study-plan.json']
        if plan.exists():
            with controller_file(plan, 'r') as reader:
                saved_definition = parse_json(reader.read())
            if saved_definition != definition:
                raise ValueError('frozen study definition differs; use a new output directory')
        else:
            if any(p.name not in ('.study.lock', '.trial-claims') for p in output.iterdir()):
                raise ValueError('existing output has no frozen study definition')
            atomic_json(plan, definition)
        jobs = [(config, repeat, confined_file(output, f'{config["name"]}/repeat-{repeat:03d}'))
                for config in configs for repeat in range(1, repeats + 1)]
        rows = {}
        pending = []
        for config, repeat, path in jobs:
            key = f'{config["name"]}/repeat-{repeat:03d}'
            if path.exists():
                if not verify_run(path)['ok']:
                    raise ValueError('incomplete or invalid existing trial; do not splice: ' + key)
                run = parse_json((path / 'run.json').read_text())
                if run['dataset_sha256'] != definition['dataset_sha256'] or run['source_sha256'] != definition['source_sha256']:
                    raise ValueError('existing trial has different data or source: ' + key)
                if run['agent'] != config['name'] or run['configuration'] != public_configuration(config):
                    raise ValueError('existing trial has different configuration: ' + key)
                rows[key] = trial_summary(key, run, reused=True)
            else:
                claim = confined_file(output, '.trial-claims/' + key + '.json')
                if claim.exists():
                    raise ValueError('prior trial attempt is incomplete; preserve history and use a new study: ' + key)
                pending.append((config, repeat, path))
        for config, _, _ in pending:
            if config.get('base_url') and not os.environ.get(config.get('api_key_env', '')):
                raise ValueError('required API credential environment is unavailable')
        # Reserve every attempt before launching any worker; reservation failures abort the study.
        for config, repeat, _ in pending:
            key = f'{config["name"]}/repeat-{repeat:03d}'
            claim = confined_file(output, '.trial-claims/' + key + '.json')
            claim.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with controller_file(claim, 'x') as ticket:
                ticket.write(json.dumps({'trial': key, 'definition_sha256': digest(definition),
                                         'configuration_sha256': definition['configurations'][config['name']]}) + '\n')
        lock = threading.Lock()
        secrets = {os.environ[c['api_key_env']] for c in configs if c.get('api_key_env') and os.environ.get(c['api_key_env'])}
        def event(key, value):
            item = {'trial': key, **value}
            with lock:
                with controller_file(confined_file(output, 'events.jsonl'), 'a') as log:
                    log.write(json.dumps(item, ensure_ascii=False) + '\n')
                if progress:
                    progress(item)
        def worker(config, repeat, path):
            key = f'{config["name"]}/repeat-{repeat:03d}'
            if (source_fingerprint() != definition['source_sha256']
                    or sha256(Path(__file__).read_bytes()) != SCHEDULER_SHA256):
                raise ValueError('source changed before trial launch')
            run = run_benchmark(data, config, path, python=python, progress=lambda e: event(key, e))
            if run['source_sha256'] != definition['source_sha256'] or not verify_run(path)['ok']:
                raise ValueError('trial source or evidence verification failed')
            return key, trial_summary(key, run)
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = {pool.submit(worker, *job): job for job in pending}
            for future in as_completed(futures):
                config, repeat, _ = futures[future]
                key = f'{config["name"]}/repeat-{repeat:03d}'
                try:
                    key, row = future.result()
                except Exception as exc:
                    row = {'trial': key, 'finished': False, 'error': redact(str(exc), secrets), 'reused': False}
                rows[key] = row
                atomic_json(controls['study-progress.json'], {'runs': [rows[k] for k in sorted(rows)]})
        result = {'schema': 'kmb.study/v1', 'definition': definition,
                  'runs': [rows[k] for k in sorted(rows)],
                  'requested_runs': len(jobs), 'finished_runs': sum(r['finished'] for r in rows.values()),
                  'reused_runs': sum(r['reused'] for r in rows.values()),
                  'stage_errors': sum(r.get('stage_errors', 0) for r in rows.values()),
                  'source_unchanged': source_fingerprint() == definition['source_sha256'],
                  'scheduler_unchanged': sha256(Path(__file__).read_bytes()) == SCHEDULER_SHA256}
        atomic_json(controls['study.json'], result)
        build_manifest(output)
        return result


def trial_summary(key, run, reused=False):
    return {'trial': key, 'run_id': run['run_id'], 'finished': True, 'reused': reused,
            'stage_count': sum(len(c['phases']) for c in run['cases']),
            'stage_errors': sum(p['status'] != 'completed' for c in run['cases'] for p in c['phases'])}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dataset', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--repeat', type=int, default=3)
    p.add_argument('--parallel', type=int, default=2)
    p.add_argument('--credential-fifo', type=Path)
    args = p.parse_args()
    data = parse_json(args.dataset.read_text())
    config = parse_json(args.config.read_text())
    if args.credential_fifo:
        names = {c['api_key_env'] for c in config.get('agents', [config]) if c.get('base_url')}
        os.environ.update(read_credentials(args.credential_fifo, names))
    result = run_study(data, config.get('agents', [config]), args.out, repeats=args.repeat,
                       parallel=args.parallel, progress=lambda e: print(json.dumps(e), flush=True))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if (result['finished_runs'] == result['requested_runs'] and result['source_unchanged']
                 and result['scheduler_unchanged']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
