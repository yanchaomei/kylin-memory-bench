"""Confined, bounded evidence collection and a content-addressed run manifest."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

from .model import canonical, digest, parse_json, relative_path, validate_dataset


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')


def confined_file(root: Path, name: str) -> Path:
    parts = relative_path(name).parts
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('symlink evidence is not accepted')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('evidence path escaped its root')
    return path


def snapshot_files(root: Path, patterns: list[str], max_bytes: int = 1024 * 1024) -> dict:
    snapshot = {'observable': bool(patterns), 'complete': True, 'scope': patterns,
                'files': [], 'errors': [], 'root_kind': 'declared_curated_memory'}
    seen = set()
    for pattern in patterns:
        relative_path(pattern)
        for path in sorted(root.glob(pattern)):
            name = path.relative_to(root).as_posix()
            if name in seen:
                continue
            seen.add(name)
            try:
                path = confined_file(root, name)
                if not path.is_file():
                    continue
                if path.stat().st_size > max_bytes or len(seen) > 500:
                    raise ValueError('memory snapshot limit exceeded')
                raw = path.read_bytes()
                text = raw.decode('utf8')
                snapshot['files'].append({'path': name, 'bytes': len(raw), 'sha256': sha256(raw), 'text': text})
            except (OSError, UnicodeError, ValueError) as exc:
                snapshot['complete'] = False
                snapshot['errors'].append({'path': name, 'error': str(exc)})
    return snapshot


def collect_artifacts(workspace: Path, paths: list[str]) -> list[dict]:
    items = []
    for name in sorted(set(paths)):
        try:
            path = confined_file(workspace, name)
            if not path.is_file():
                continue
            if path.stat().st_size > 1024 * 1024:
                items.append({'path': name, 'error': 'artifact exceeds 1 MiB'})
                continue
            raw = path.read_bytes()
            stat = path.stat()
            item = {'path': name, 'sha256': sha256(raw), 'bytes': len(raw),
                    'mtime_ns': stat.st_mtime_ns, 'ctime_ns': stat.st_ctime_ns, 'inode': stat.st_ino}
            try:
                item['raw_text'] = raw.decode('utf8')
                item['json'] = parse_json(raw.decode('utf8'))
            except (ValueError, UnicodeError):
                item['error'] = 'artifact is not UTF-8 JSON'
            items.append(item)
        except (OSError, ValueError) as exc:
            items.append({'path': name, 'error': str(exc)})
    return items


def snapshot_sqlite(root: Path, specs: list[dict]) -> dict:
    result = {'observable': bool(specs), 'complete': True, 'scope': specs, 'files': [], 'errors': [],
              'root_kind': 'declared_sqlite_memory_records'}
    for spec in specs:
        name = spec['path']
        try:
            path = confined_file(root, name)
            if not path.exists():
                continue
            if not spec['query'].strip().upper().startswith('SELECT '):
                raise ValueError('memory record query must be SELECT')
            started = time.monotonic()
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as con:
                con.set_progress_handler(lambda: int(time.monotonic() - started > 2), 1000)
                rows = con.execute(spec['query'], spec.get('params', [])).fetchmany(1001)
                if len(rows) > 1000:
                    raise ValueError('memory record row cap exceeded')
                text = json.dumps(rows, ensure_ascii=False)
                if len(text.encode()) > 1024 * 1024:
                    raise ValueError('memory record byte cap exceeded')
                result['files'].append({'path': name + '#query', 'query': spec['query'], 'text': text,
                                        'sha256': sha256(text.encode()), 'records': len(rows)})
        except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
            result['complete'] = False
            result['errors'].append({'path': name, 'error': str(exc)})
    return result


def environment() -> dict:
    release = {}
    if Path('/etc/os-release').is_file():
        for line in Path('/etc/os-release').read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep and re.fullmatch('[A-Z_]+', key):
                release[key] = value.strip('"')
    return {'system': platform.system(), 'release': platform.release(), 'machine': platform.machine(),
            'python': platform.python_version(), 'os_release': release,
            'openkylin': release.get('ID', '').lower() == 'openkylin',
            'desktop': os.environ.get('XDG_CURRENT_DESKTOP', ''), 'display_present': bool(os.environ.get('DISPLAY'))}


def build_manifest(root: Path) -> dict:
    files = []
    for path in sorted(root.rglob('*')):
        if path.is_file() and path != root / 'manifest.json':
            name = path.relative_to(root).as_posix()
            raw = confined_file(root, name).read_bytes()
            files.append({'path': name, 'bytes': len(raw), 'sha256': sha256(raw)})
    result = {'schema': 'kmb.manifest/v1', 'algorithm': 'sha256', 'files': files}
    write_json(root / 'manifest.json', result)
    return result


def verify_manifest(root: Path) -> dict:
    errors = []
    try:
        manifest = json.loads(confined_file(root, 'manifest.json').read_text())
        if manifest.get('schema') != 'kmb.manifest/v1' or not manifest.get('files'):
            raise ValueError('invalid or empty manifest')
        seen = set()
        for item in manifest['files']:
            name = item['path']
            if name == 'manifest.json' or name in seen:
                raise ValueError('duplicated or self-referencing manifest entry')
            seen.add(name)
            try:
                raw = confined_file(root, name).read_bytes()
                if len(raw) != item['bytes'] or sha256(raw) != item['sha256']:
                    errors.append({'path': name, 'error': 'hash or size mismatch'})
            except (OSError, ValueError) as exc:
                errors.append({'path': name, 'error': str(exc)})
        observed = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p != root / 'manifest.json'}
        if observed != seen:
            errors.append({'error': 'unlisted or missing evidence files', 'paths': sorted(observed ^ seen)})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append({'error': str(exc)})
    return {'ok': not errors, 'errors': errors}


def verify_run(root: Path) -> dict:
    """Check the run evidence graph as well as the file inventory."""
    result = verify_manifest(root)
    if not result['ok']:
        return result
    errors = result['errors']
    try:
        data = parse_json(confined_file(root, 'dataset.json').read_text())
        run = parse_json(confined_file(root, 'run.json').read_text())
        validate_dataset(data)
        if run.get('schema') != 'kmb.run/v1' or run.get('dataset_sha256') != digest(data):
            raise ValueError('run schema or dataset fingerprint mismatch')
        if not run.get('finished_at') or not run.get('run_id'):
            raise ValueError('run is not finalized')
        if run.get('config_sha256') != digest(run['configuration']):
            raise ValueError('configuration fingerprint mismatch')
        if run.get('source_sha256') != digest(run['source_files']):
            raise ValueError('source fingerprint mismatch')
        observed_cases = run['cases']
        if [c['id'] for c in observed_cases] != [c['id'] for c in data['cases']]:
            raise ValueError('case inventory or order mismatch')
        sessions = set()
        from .adapters import parse_response
        for case, observed in zip(data['cases'], observed_cases):
            phases = observed['phases']
            if [p['phase_id'] for p in phases] != [p['id'] for p in case['phases']]:
                raise ValueError('phase inventory or order mismatch')
            native_sessions = set()
            for expected, phase in zip(case['phases'], phases):
                session = phase['session_id']
                if not isinstance(session, str) or not session or session in sessions:
                    raise ValueError('conversation session repeated or absent')
                sessions.add(session)
                native = phase.get('native_metadata', {}).get('native_session_id')
                if native:
                    if native in native_sessions:
                        raise ValueError('native conversation session repeated')
                    native_sessions.add(native)
                folder = Path('evidence') / case['id'] / expected['id']
                refs = [(folder / name).as_posix() for name in ('request.json', 'process.json', 'stdout.txt', 'stderr.txt', 'response.txt', 'phase.json')]
                if phase.get('evidence_refs') != refs:
                    raise ValueError('required stage evidence references missing or inconsistent')
                for name in refs:
                    if not confined_file(root, name).is_file():
                        raise ValueError('required stage file missing: ' + name)
                observed_file = parse_json(confined_file(root, (folder / 'phase.json').as_posix()).read_text())
                if canonical(observed_file) != canonical(phase):
                    raise ValueError('phase record differs from run record')
                request = parse_json(confined_file(root, (folder / 'request.json').as_posix()).read_text())
                if set(request) != {'schema', 'case_id', 'phase_id', 'kind', 'session_id', 'message', 'workspace'}:
                    raise ValueError('request whitelist mismatch')
                if any(request[k] != v for k, v in {'schema': 'kmb.request/v1', 'case_id': case['id'],
                         'phase_id': expected['id'], 'kind': expected['kind'], 'session_id': session, 'message': expected['message']}.items()):
                    raise ValueError('request does not match frozen case')
                process = parse_json(confined_file(root, (folder / 'process.json').as_posix()).read_text())
                if process['returncode'] != phase['returncode'] or process['elapsed_ms'] != phase['elapsed_ms']:
                    raise ValueError('process record differs from phase record')
                response = confined_file(root, (folder / 'response.txt').as_posix()).read_bytes().decode('utf8')
                if response != phase['response']:
                    raise ValueError('reply file differs from scored reply')
                if phase['status'] == 'completed':
                    if process['status'] != 'completed' or phase['returncode'] != 0:
                        raise ValueError('completed phase has a failed process')
                    stdout = confined_file(root, (folder / 'stdout.txt').as_posix()).read_bytes().decode('utf8')
                    parsed, meta = parse_response(run['configuration']['adapter'], stdout)
                    if parsed != response or canonical(meta) != canonical(phase['native_metadata']):
                        raise ValueError('native stdout does not match scored response')
                before = {a['path']: a for a in phase.get('artifacts_before', [])}
                for item in phase.get('artifacts', []):
                    if 'json' not in item:
                        continue
                    text = item['raw_text']
                    if sha256(text.encode()) != item['sha256'] or canonical(parse_json(text)) != canonical(item['json']):
                        raise ValueError('task artifact content or fingerprint mismatch')
                    old = before.get(item['path'])
                    fresh = old is None or any(item.get(k) != old.get(k) for k in ('sha256', 'mtime_ns', 'ctime_ns', 'inode'))
                    if item.get('fresh') != fresh:
                        raise ValueError('task artifact freshness is inconsistent')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.append({'error': str(exc)})
    return {'ok': not errors, 'errors': errors}
