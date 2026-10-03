import json
import sys
import tempfile
import unittest
from pathlib import Path

from kylin_memory_bench.dataset import generate
from kylin_memory_bench.evidence import snapshot_files, snapshot_sqlite, verify_manifest, verify_run
from kylin_memory_bench.runner import run_benchmark
from kylin_memory_bench.scoring import score_run


class RunnerTests(unittest.TestCase):
    def fixture(self, root, mode='perfect'):
        return run_benchmark(generate(19, 4), {'name': mode, 'adapter': 'fixture', 'mode': mode}, root,
                             python=sys.executable)

    def test_perfect_fixture_runs_processes_and_real_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'run'
            run = self.fixture(root)
            score = score_run(generate(19, 4), run)
            self.assertTrue(all(d['score'] == 1 and d['coverage'] == 1 for d in score['dimensions'].values()))
            sessions = [p['session_id'] for c in run['cases'] for p in c['phases']]
            self.assertEqual(len(sessions), len(set(sessions)))
            self.assertTrue(verify_manifest(root)['ok'])
            self.assertTrue(verify_run(root)['ok'], 'full run graph verification failed')
            target = next((root / 'evidence').rglob('response.txt'))
            target.write_text('tampered')
            self.assertFalse(verify_manifest(root)['ok'])

    def test_unlisted_nested_manifest_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'run'
            self.fixture(root)
            hidden = root / 'unexpected/manifest.json'; hidden.parent.mkdir()
            hidden.write_text('{}')
            self.assertFalse(verify_manifest(root)['ok'])

    def test_session_only_fixture_separates_boundary_from_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.fixture(Path(tmp) / 'run', 'session-only')
            score = score_run(generate(19, 4), run)
            self.assertEqual(score['dimensions']['boundary']['score'], 0)
            self.assertGreater(score['outcome_counts'].get('correct', 0), 0)
            self.assertEqual(score['dimensions']['persistence']['score'], 0)
            self.assertEqual(score['dimensions']['reuse']['score'], 0)

    def test_stale_unsafe_claim_only_controls(self):
        for mode, outcome in [('stale', 'stale_update'), ('unsafe', 'incorrect_persistence'), ('claim-only', 'incorrect_reuse')]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                score = score_run(generate(19, 4), self.fixture(Path(tmp) / 'run', mode))
                self.assertGreater(score['outcome_counts'].get(outcome, 0), 0)

    def test_action_claim_control_keeps_memory_but_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            score = score_run(generate(19, 4), self.fixture(Path(tmp) / 'run', 'claim-only'))
            self.assertEqual(score['dimensions']['reuse']['score'], 0)
            self.assertTrue(all(score['dimensions'][d]['score'] == 1 for d in score['dimensions'] if d != 'reuse'))

    def test_symlink_and_size_cap_cannot_fake_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'memory.txt').write_text('0123456789')
            self.assertFalse(snapshot_files(root, ['memory.txt'], max_bytes=3)['complete'])
            (root / 'link.txt').symlink_to(root / 'memory.txt')
            self.assertFalse(snapshot_files(root, ['link.txt'])['complete'])
            self.assertFalse(snapshot_files(root, [])['observable'])

    def test_refuses_to_overwrite_existing_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):
                self.fixture(Path(tmp))

    def test_sqlite_memory_snapshot_is_readonly_and_bounded(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            con = sqlite3.connect(root / 'memory.db')
            con.execute('CREATE TABLE memory (value TEXT)')
            con.execute('INSERT INTO memory VALUES (?)', ('test-value',))
            con.commit(); con.close()
            result = snapshot_sqlite(root, [{'path': 'memory.db', 'query': 'SELECT value FROM memory'}])
            self.assertTrue(result['complete'])
            self.assertIn('test-value', result['files'][0]['text'])
            result = snapshot_sqlite(root, [{'path': 'memory.db', 'query': 'DELETE FROM memory'}])
            self.assertFalse(result['complete'])


if __name__ == '__main__':
    unittest.main()
