import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from kylin_memory_bench.dataset import generate
from kylin_memory_bench.evidence import verify_run
from kylin_memory_bench.runner import run_benchmark


def study_module():
    path = Path(__file__).resolve().parents[1] / 'scripts/run_study.py'
    spec = importlib.util.spec_from_file_location('kmb_study', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StudyTests(unittest.TestCase):
    def test_stage_failures_remain_finished_evidence_and_are_not_selectively_retried(self):
        study = study_module()
        data = generate(19, 1)
        config = {'name': 'synthetic-failure', 'adapter': 'json-command',
                  'command': [sys.executable, '-c', 'raise SystemExit(3)']}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'study'
            first = study.run_study(data, [config], root, repeats=1, parallel=1, python=sys.executable)
            self.assertEqual(first['finished_runs'], 1)
            self.assertEqual(first['stage_errors'], 22)
            saved = (root / 'synthetic-failure/repeat-001/run.json').read_bytes()
            second = study.run_study(data, [config], root, repeats=1, parallel=1, python=sys.executable)
            self.assertEqual(second['reused_runs'], 1)
            self.assertEqual(second['stage_errors'], 22)
            self.assertEqual(saved, (root / 'synthetic-failure/repeat-001/run.json').read_bytes())

    def test_partial_trial_and_changed_frozen_plan_cannot_be_resumed(self):
        study = study_module()
        data = generate(19, 1)
        config = {'name': 'perfect', 'adapter': 'fixture', 'mode': 'perfect'}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'study'
            study.run_study(data, [config], root, repeats=1, parallel=1, python=sys.executable)
            with self.assertRaisesRegex(ValueError, 'definition'):
                study.run_study(data, [config], root, repeats=2, parallel=1, python=sys.executable)
            (root / 'perfect/repeat-001/manifest.json').unlink()
            with self.assertRaisesRegex(ValueError, 'incomplete or invalid'):
                study.run_study(data, [config], root, repeats=1, parallel=1, python=sys.executable)
    def test_fifo_credentials_are_read_once_without_a_regular_secret_file(self):
        import os
        import threading
        study = study_module()
        read_credentials = study.read_credentials
        with tempfile.TemporaryDirectory() as tmp:
            fifo = Path(tmp) / 'credential.fifo'
            os.mkfifo(fifo, 0o600)
            def write():
                with fifo.open('w') as f:
                    json.dump({'KMB_TEST_KEY': 'synthetic-private-value'}, f)
            writer = threading.Thread(target=write)
            writer.start()
            result = read_credentials(fifo, {'KMB_TEST_KEY'}, timeout=3)
            writer.join(timeout=3)
            self.assertFalse(writer.is_alive())
            self.assertEqual(result, {'KMB_TEST_KEY': 'synthetic-private-value'})
            self.assertFalse(fifo.exists())
            regular = Path(tmp) / 'not-a-pipe'
            regular.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'FIFO'):
                study.read_credentials(regular, {'KMB_TEST_KEY'}, timeout=1)
    def test_resume_rejects_valid_evidence_from_a_different_configuration(self):
        import shutil
        study = study_module()
        data = generate(19, 1)
        config = {'name': 'same-name', 'adapter': 'fixture', 'mode': 'perfect'}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'study'
            study.run_study(data, [config], root, repeats=1, parallel=1, python=sys.executable)
            original = root / 'same-name/repeat-001'
            replacement = Path(tmp) / 'replacement'
            run_benchmark(data, dict(config, mode='session-only'), replacement, python=sys.executable)
            shutil.rmtree(original)
            shutil.copytree(replacement, original)
            self.assertTrue(verify_run(original)['ok'])
            with self.assertRaisesRegex(ValueError, 'configuration'):
                study.run_study(data, [config], root, repeats=1, parallel=1, python=sys.executable)
    def test_independent_repeats_run_in_parallel_and_resume_without_replacing_evidence(self):
        study = study_module()
        data = generate(19, 1)
        configs = [{'name': 'perfect', 'adapter': 'fixture', 'mode': 'perfect'}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'study'
            result = study.run_study(data, configs, root, repeats=2, parallel=2, python=sys.executable)
            self.assertEqual(result['finished_runs'], 2)
            self.assertEqual(result['stage_errors'], 0)
            paths = sorted(root.glob('perfect/repeat-*'))
            self.assertEqual(len(paths), 2)
            self.assertTrue(all(verify_run(p)['ok'] for p in paths))
            before = [(p / 'run.json').read_bytes() for p in paths]
            ids = [json.loads(x)['run_id'] for x in before]
            self.assertEqual(len(set(ids)), 2)
            result = study.run_study(data, configs, root, repeats=2, parallel=2, python=sys.executable)
            self.assertEqual(result['reused_runs'], 2)
            self.assertEqual(before, [(p / 'run.json').read_bytes() for p in paths])
