import copy
import json
import os
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from kylin_memory_bench.adapters import Adapter, parse_response, validate_config
from kylin_memory_bench.dataset import generate
from kylin_memory_bench import evidence
from kylin_memory_bench.evidence import build_manifest, write_json
from kylin_memory_bench.model import digest, validate_dataset
from kylin_memory_bench.reporting import compare_scores
from kylin_memory_bench.runner import execute, run_benchmark
from kylin_memory_bench.scoring import evaluate_assertion, score_run


class ReviewRegressions(unittest.TestCase):
    def test_dot_components_are_not_identifiers(self):
        for name in ('.', '..'):
            data = generate(1, 1)
            data['cases'][0]['id'] = name
            with self.assertRaises(ValueError):
                validate_dataset(data)
            data = generate(1, 1)
            data['cases'][0]['phases'][0]['id'] = name
            with self.assertRaises(ValueError):
                validate_dataset(data)
            with self.assertRaises(ValueError):
                validate_config({'name': name, 'adapter': 'fixture'})

    def test_boundary_scans_all_response_fields(self):
        case = generate(1, 1)['cases'][4]
        rule = next(r for r in case['assertions'] if r['type'] == 'response_absent')
        text = json.dumps({'answer': None, 'leak': rule['forbidden'][0]})
        result = evaluate_assertion(case, rule, {'status': 'completed', 'response': text})
        self.assertIs(result['passed'], False)
        escaped = ''.join('\\u%04x' % ord(c) for c in rule['forbidden'][0])
        for text in ('{"answer":null,"leak":"' + escaped + '"}', 'Leaked: ' + rule['forbidden'][0]):
            with self.subTest(response=text):
                result = evaluate_assertion(case, rule, {'status': 'completed', 'response': text})
                self.assertIs(result['passed'], False)

    def test_boundary_storage_is_checked_after_every_phase(self):
        case = generate(1, 1)['cases'][4]
        checked = {r['phase'] for r in case['assertions'] if r['type'] == 'memory_absent'}
        self.assertEqual(checked, {p['id'] for p in case['phases']})

    def test_unchanged_artifact_is_not_an_action(self):
        case = generate(1, 1)['cases'][-1]
        rule = case['assertions'][0]
        result = evaluate_assertion(case, rule, {'status': 'completed', 'artifacts': [
            {'path': rule['path'], 'json': rule['expected'], 'fresh': False, 'sha256': 'test'}]})
        self.assertFalse(result['passed'])

    def test_invalid_native_envelope_is_a_protocol_error(self):
        for text in ('[]', 'null', '{"result":null}', '{"payloads":[null]}', '{"payloads":[{"text":"{}"}],"meta":{"agentMeta":{"lastCallUsage":1}}}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_response('openclaw', text)

    def test_mismatched_repeat_conditions_are_not_pooled(self):
        data = generate(1, 1)
        run = {'run_id': 'a', 'agent': 'A', 'agent_kind': 'fixture', 'environment': {}, 'dataset_sha256': digest(data),
               'cases': [], 'configuration': {'model': 'a'}, 'agent_version': '1'}
        a = score_run(data, run)
        b = copy.deepcopy(a); b['run_id'] = 'b'; b['configuration']['model'] = 'b'; b['agent_version'] = '2'
        with self.assertRaises(ValueError):
            compare_scores([a, b])

    def test_provider_config_key_is_in_redaction_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'source'
            auth = source / 'agents/main/agent'; auth.mkdir(parents=True)
            (auth / 'auth-profiles.json').write_text('{}')
            write_json(source / 'openclaw.json', {'models': {'providers': {'example': {'apiKey': 'synthetic-secret-in-provider'}}}})
            adapter = Adapter({'name': 'test', 'adapter': 'openclaw', 'model': 'example/test',
                               'credential_home': str(source), 'copy_provider_config': True}, root / 'p', root / 'w', sys.executable)
            self.assertTrue('synthetic-secret-in-provider' in adapter.secrets, 'provider secret was not registered for redaction')

    def test_config_and_argv_do_not_export_known_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'run'
            data = generate(1, 1); data['cases'] = data['cases'][:1]
            secret = 'synthetic-test-key-never-publish'
            config = {'name': 'fake-bridge', 'adapter': 'json-command', 'command': ['bridge', '--api-key', secret], 'env': {'API_KEY': secret}}
            with patch('kylin_memory_bench.runner.execute', return_value={'status': 'completed', 'returncode': 0, 'stdout': '{"response":"{\\"answer\\":null}"}', 'stderr': '', 'elapsed_ms': 1}):
                run_benchmark(data, config, root)
            for p in root.rglob('*'):
                if p.is_file():
                    self.assertNotIn(secret, p.read_text())

    def test_manifest_without_stage_evidence_is_not_a_valid_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / 'dataset.json', generate(1, 1))
            write_json(root / 'run.json', {'schema': 'kmb.run/v1', 'cases': []})
            build_manifest(root)
            verifier = getattr(evidence, 'verify_run', evidence.verify_manifest)
            self.assertFalse(verifier(root)['ok'])

    def test_timeout_exit_race_still_records_a_timeout(self):
        import subprocess
        from unittest.mock import MagicMock
        process = MagicMock(pid=987654, returncode=-15)
        process.communicate.side_effect = subprocess.TimeoutExpired('synthetic', .01)
        with tempfile.TemporaryDirectory() as tmp, patch('kylin_memory_bench.runner.subprocess.Popen', return_value=process), patch('kylin_memory_bench.runner.os.killpg', side_effect=ProcessLookupError):
            result = execute(['fake'], env={}, cwd=Path(tmp), request={}, timeout=.01)
            self.assertEqual(result['status'], 'timeout')

    @unittest.skipUnless(hasattr(os, 'fork'), 'POSIX process groups required')
    def test_timeout_reaps_children_that_ignore_sigterm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = ("import os,signal,time,pathlib; "
                      "pid=os.fork(); "
                      "pathlib.Path('child.pid').write_text(str(pid)) if pid else None; "
                      "signal.signal(signal.SIGTERM, signal.SIG_IGN) if not pid else None; "
                      "time.sleep(1) if not pid else time.sleep(10); "
                      "pathlib.Path('alive').write_text('still-running') if not pid else None")
            result = execute([sys.executable, '-c', script], env=os.environ.copy(), cwd=root, request={}, timeout=.3)
            time.sleep(1.1)
            self.assertEqual(result['status'], 'timeout')
            self.assertFalse((root / 'alive').exists())


if __name__ == '__main__':
    unittest.main()
