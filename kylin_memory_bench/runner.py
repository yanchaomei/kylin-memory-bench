"""One process per phase, isolated case profiles, incremental hashed evidence."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .adapters import HERE, Adapter, parse_response, validate_config
from .evidence import build_manifest, collect_artifacts, environment, sha256, write_json
from .model import adapter_request, digest, validate_dataset
from .privacy import redact, redact_object
from .scoring import score_run


def execute(command: list[str], *, env: dict, cwd: Path, request: dict, timeout: float) -> dict:
    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
        except OSError as exc:
            return {'status': 'failed', 'returncode': None, 'stdout': '', 'stderr': str(exc), 'elapsed_ms': 0}
        status = 'completed'
        try:
            process.communicate(json.dumps(request, ensure_ascii=False).encode(), timeout=timeout)
        except subprocess.TimeoutExpired:
            status = 'timeout'
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        finally:
            # A reaped parent does not imply its worker children have stopped.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.returncode and status == 'completed':
            status = 'failed'
        result = {'status': status, 'returncode': process.returncode,
                  'elapsed_ms': round((time.monotonic() - started) * 1000, 3)}
        for name, file in [('stdout', stdout), ('stderr', stderr)]:
            file.seek(0, 2)
            size = file.tell()
            file.seek(0)
            result[name] = file.read(2 * 1024 * 1024).decode('utf8', errors='replace')
            result[name + '_bytes'] = size
            if size > 2 * 1024 * 1024:
                result['status'] = 'output_limit'
        return result


def run_benchmark(dataset: dict, config: dict, output: Path, *, python: str = sys.executable, progress=None) -> dict:
    validate_dataset(dataset)
    validate_config(config)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    run_id = config['name'] + '-' + str(uuid.uuid4())
    public_config = {k: v for k, v in config.items() if k not in {'credential_home', 'env'}}
    source_files = {p.name: sha256(p.read_bytes()) for p in sorted((HERE / 'kylin_memory_bench').glob('*.py'))}
    agent_version = None
    if config['adapter'] in {'openclaw', 'hermes'}:
        argv = [config.get('executable', config['adapter']), '--version' if config['adapter'] == 'openclaw' else 'version']
        try:
            v = subprocess.run(argv, capture_output=True, text=True, timeout=12)
            agent_version = v.stdout.splitlines()[0] if v.stdout else 'version unavailable'
        except (OSError, subprocess.TimeoutExpired):
            agent_version = 'version probe unavailable'
    run = {'schema': 'kmb.run/v1', 'run_id': run_id, 'agent': config['name'],
           'agent_kind': 'fixture' if config['adapter'] == 'fixture' else 'real',
           'dataset_sha256': digest(dataset), 'config_sha256': digest(public_config),
           'configuration': public_config, 'environment': environment(),
           'agent_version': agent_version, 'source_files': source_files, 'source_sha256': digest(source_files),
           'started_at': datetime.now(timezone.utc).isoformat(), 'cases': [],
           'session_policy': 'fresh process and fresh conversation per phase, durable state only within each case'}
    write_json(output / 'dataset.json', dataset)
    total = sum(len(c['phases']) for c in dataset['cases'])
    completed = 0
    # Credential-bearing profiles and agent-owned files live outside the shareable evidence bundle.
    with tempfile.TemporaryDirectory(prefix='kmb-private-') as tmp:
        private_root = Path(tmp)
        for case in dataset['cases']:
            row = {'id': case['id'], 'phases': []}
            run['cases'].append(row)
            adapter = Adapter(config, private_root / case['id'] / 'profile', private_root / case['id'] / 'workspace', python)
            if config['adapter'] == 'json-command':
                argv = config.get('command', [])
                for i, arg in enumerate(argv[:-1]):
                    if arg in {'--api-key', '--token', '--password', '--secret'}:
                        adapter.secrets.add(argv[i+1])
            run['configuration'] = redact_object(public_config, adapter.secrets)
            run['configuration']['environment_keys'] = sorted(config.get('env', {}))
            run['config_sha256'] = digest(run['configuration'])
            native_sessions = set()
            for phase in case['phases']:
                session_id = str(uuid.uuid4())
                request = adapter_request(case, phase, session_id=session_id, workspace=str(adapter.workspace))
                adapter.prepare_phase()
                command = adapter.command(request)
                artifact_paths = sorted({r['path'] for r in case['assertions']
                                         if r['type'] in ('artifact_json', 'artifact_absent') and r['phase'] == phase['id']})
                artifacts_before = collect_artifacts(adapter.workspace, artifact_paths)
                result = execute(command, env=adapter.env, cwd=adapter.workspace, request=request, timeout=float(config.get('timeout', 180)))
                result['stdout'] = redact(result['stdout'], adapter.secrets)
                result['stderr'] = redact(result['stderr'], adapter.secrets)
                observed = {'phase_id': phase['id'], 'kind': phase['kind'], 'session_id': session_id,
                            'status': result['status'], 'returncode': result['returncode'],
                            'elapsed_ms': result['elapsed_ms'], 'response': '', 'native_metadata': {}}
                if observed['status'] == 'completed':
                    try:
                        observed['response'], observed['native_metadata'] = parse_response(config['adapter'], result['stdout'])
                        native = observed['native_metadata'].get('native_session_id')
                        if native and native in native_sessions:
                            raise ValueError('adapter reused a native conversation across phases')
                        if native:
                            native_sessions.add(native)
                    except (ValueError, KeyError, TypeError) as exc:
                        observed.update(status='protocol_error', error=str(exc))
                observed['memory_snapshot'] = adapter.memory_snapshot()
                observed['action_trace'] = adapter.trace(request, observed['native_metadata'])
                observed['artifacts'] = collect_artifacts(adapter.workspace, artifact_paths)
                observed['artifact_scope'] = artifact_paths
                observed['artifacts_before'] = artifacts_before
                before_index = {item['path']: item for item in artifacts_before}
                for item in observed['artifacts']:
                    old = before_index.get(item['path'])
                    item['fresh'] = old is None or any(item.get(k) != old.get(k) for k in ('sha256', 'mtime_ns', 'ctime_ns', 'inode'))
                observed = redact_object(observed, adapter.secrets)
                folder = output / 'evidence' / case['id'] / phase['id']
                write_json(folder / 'request.json', request)
                # Messages are already in request.json; argv retains flags without repeating long prompts.
                write_json(folder / 'process.json', {'argv': [redact(a, adapter.secrets) if a != request['message'] else '<request.message>' for a in command],
                                                   'status': result['status'], 'returncode': result['returncode'],
                                                   'elapsed_ms': result['elapsed_ms']})
                (folder / 'stdout.txt').write_text(result['stdout'], encoding='utf8')
                (folder / 'stderr.txt').write_text(result['stderr'], encoding='utf8')
                (folder / 'response.txt').write_text(observed['response'], encoding='utf8')
                observed['evidence_refs'] = [str((folder / f).relative_to(output)) for f in ('request.json', 'process.json', 'stdout.txt', 'stderr.txt', 'response.txt', 'phase.json')]
                write_json(folder / 'phase.json', observed)
                row['phases'].append(observed)
                completed += 1
                write_json(output / 'run.json', run)
                if progress:
                    progress({'agent': config['name'], 'case': case['id'], 'phase': phase['id'], 'status': observed['status'],
                              'completed': completed, 'total': total, 'elapsed_ms': observed['elapsed_ms']})
    run['finished_at'] = datetime.now(timezone.utc).isoformat()
    write_json(output / 'run.json', run)
    write_json(output / 'score.json', score_run(dataset, run))
    build_manifest(output)
    return run
