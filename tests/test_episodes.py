import tempfile
import importlib
import copy
import sys
import unittest
from pathlib import Path

from kylin_memory_bench.dataset import block, fact, write_message
from kylin_memory_bench.fixture import respond
from kylin_memory_bench.model import adapter_request, digest, validate_dataset
from kylin_memory_bench.scoring import evaluate_assertion
from kylin_memory_bench.runner import run_benchmark
from kylin_memory_bench.evidence import verify_run
from kylin_memory_bench.evidence import build_manifest, write_json
from kylin_memory_bench.scoring import score_run
from kylin_memory_bench.paired import summarize_pairs
from kylin_memory_bench.cli import main
from kylin_memory_bench.reporting import render_report


class EpisodeTests(unittest.TestCase):
    def test_missing_memory_file_list_is_unobservable_and_new_protocol_cannot_downgrade(self):
        rule = {'id': 'privacy', 'phase': 'p', 'type': 'memory_absent', 'forbidden': ['FORBIDDEN_MARKER']}
        phase = {'status': 'completed', 'memory_snapshot': {'observable': True, 'complete': True}}
        self.assertIsNone(evaluate_assertion({'dimension': 'boundary'}, rule, phase)['passed'])
        generate = importlib.import_module('kylin_memory_bench.episodes').generate_episodes
        data = generate(7, 'test', 1, 1)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            run = run_benchmark(data, {'name': 'perfect', 'adapter': 'fixture', 'mode': 'perfect'}, out, python=sys.executable)
            case = next(c for c in run['cases'] if c['id'] == next(
                d['id'] for d in data['cases'] if d['dimension'] == 'reuse' and d['intervention']['arm'] == 'provided'))
            p = next(p for p in case['phases'] if p['phase_id'] == 'reuse')
            for key in ('artifact_scope', 'artifacts', 'artifacts_before'):
                p.pop(key)
            write_json(out / 'run.json', run)
            write_json(out / 'evidence' / case['id'] / 'reuse/phase.json', p)
            build_manifest(out)
            self.assertFalse(verify_run(out)['ok'])
    def test_registered_interventions_reject_same_sources_duplicate_tasks_and_null_goals(self):
        generate = importlib.import_module('kylin_memory_bench.episodes').generate_episodes
        data = generate(7, 'test', 1, 1)
        one = copy.deepcopy(data)
        a, b = one['cases'][:2]
        b['phases'] = copy.deepcopy(a['phases'])
        b['facts'] = copy.deepcopy(a['facts'])
        with self.assertRaises(ValueError):
            validate_dataset(one)
        one = copy.deepcopy(data)
        extra = copy.deepcopy(one['cases'])
        for c in extra:
            c['id'] += '-duplicate'
            c['intervention']['pair_id'] += '-duplicate'
        one['cases'].extend(extra)
        with self.assertRaises(ValueError):
            validate_dataset(one)
        one = copy.deepcopy(data)
        for c in one['cases'][:2]:
            c['intervention']['objective']['expected'] = None
        with self.assertRaises(ValueError):
            validate_dataset(one)

    def test_missing_observations_do_not_pass_or_create_a_positive_gain(self):
        generate = importlib.import_module('kylin_memory_bench.episodes').generate_episodes
        data = generate(7, 'test', 1, 1)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            run = run_benchmark(data, {'name': 'perfect', 'adapter': 'fixture', 'mode': 'perfect'}, out, python=sys.executable)
            case = next(c for c in data['cases'] if c['dimension'] == 'reuse' and c['intervention']['arm'] == 'withheld')
            observed = next(c for c in run['cases'] if c['id'] == case['id'])
            phase = next(p for p in observed['phases'] if p['phase_id'] == 'reuse')
            phase['artifacts'] = [{'path': 'handover.json', 'error': 'unreadable collector target'}]
            score = score_run(data, run)
            row = next(c for c in score['cases'] if c['case_id'] == case['id'])
            self.assertIsNone(row['target_attainment']['passed'])
            paired = summarize_pairs([score])
            self.assertEqual(paired['complete_pairs'], 5)
            self.assertLess(paired['complete_pair_coverage'], 1)
            phase.pop('artifacts')
            score = score_run(data, run)
            row = next(c for c in score['cases'] if c['case_id'] == case['id'])
            self.assertIsNone(row['passed'])
            write_json(out / 'run.json', run)
            write_json(out / 'evidence' / case['id'] / 'reuse/phase.json', phase)
            build_manifest(out)
            self.assertFalse(verify_run(out)['ok'])
    def test_reuse_episode_checks_action_feedback_and_a_second_action(self):
        generate = importlib.import_module('kylin_memory_bench.episodes').generate_episodes
        data = generate(7, 'test', 1, 2)
        case = next(c for c in data['cases'] if c['dimension'] == 'reuse' and c['intervention']['arm'] == 'provided')
        kinds = [p['kind'] for p in case['phases']]
        self.assertEqual(kinds.count('action'), 2)
        self.assertIn('update', kinds)
        files = [r for r in case['assertions'] if r['type'] == 'artifact_json']
        self.assertEqual({r['path'] for r in files}, {'checkpoint.json', 'handover.json'})
        before = next(r['expected'] for r in files if r['path'] == 'checkpoint.json')
        after = next(r['expected'] for r in files if r['path'] == 'handover.json')
        self.assertEqual(before['deployment_path'], after['deployment_path'])
        self.assertNotEqual(before['handover_code'], after['handover_code'])
    def test_episode_cli_generation_and_report_include_pair_metrics(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_path = root / 'data.json'
            self.assertEqual(main(['generate-episodes', '--seed', '7', '--split', 'test', '--per-dimension', '1',
                                   '--interference-sessions', '1', '--out', str(dataset_path)]), 0)
            data = json.loads(dataset_path.read_text())
            out = root / 'run'
            run_benchmark(data, {'name': 'perfect', 'adapter': 'fixture', 'mode': 'perfect'}, out, python=sys.executable)
            score = json.loads((out / 'score.json').read_text())
            report = render_report([score], root / 'report')
            self.assertEqual(report['agents'][0]['paired_summary']['mean_source_gain'], 1.0)
            self.assertIn('配对资料收益', (root / 'report/report.html').read_text())
            self.assertIn('+100.0 pp', (root / 'report/report.html').read_text())
            self.assertTrue((root / 'report/paired_metrics.csv').is_file())

    def test_development_and_test_fact_worlds_are_disjoint_and_boundaries_are_stratified(self):
        generate = importlib.import_module('kylin_memory_bench.episodes').generate_episodes
        development = generate(11, 'development', 4, 4)
        test = generate(11, 'test', 4, 4)
        def values(data):
            return {f['value'] for c in data['cases'] for f in c['facts']}
        self.assertFalse(values(development) & values(test))
        self.assertEqual(len(test['cases']), 48)
        self.assertEqual({f['policy'] for c in test['cases'] if c['dimension'] == 'boundary'
                          for f in c['facts'] if f['policy'] != 'retain'},
                         {'session_only', 'sensitive', 'risk', 'noise'})
        for case in test['cases']:
            self.assertEqual(sum(p['id'].startswith('gap') for p in case['phases']), 4)
            for p in case['phases']:
                if p['kind'] in ('query', 'action'):
                    self.assertFalse(any(f['value'] in p['message'] for f in case['facts']))
    def test_real_process_calibration_separates_safe_abstention_from_memory_utility(self):
        module = importlib.import_module('kylin_memory_bench.episodes')
        data = module.generate_episodes(7, 'test', 1, 1)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            run_benchmark(data, {'name': 'perfect', 'adapter': 'fixture', 'mode': 'perfect'}, out, python=sys.executable)
            self.assertTrue(verify_run(out)['ok'])
            import json
            score = json.loads((out / 'score.json').read_text())
            self.assertTrue(all(c['passed'] for c in score['cases']))
            for case in score['cases']:
                expected = case['intervention']['arm'] == 'provided'
                self.assertEqual(case['target_attainment']['passed'], expected)
    def test_episode_import_rejects_incomplete_pairs_and_changed_queries(self):
        generate = importlib.import_module('kylin_memory_bench.episodes').generate_episodes
        data = generate(7, 'test', 1, 2)
        broken = copy.deepcopy(data)
        broken['cases'].pop()
        with self.assertRaisesRegex(ValueError, 'pair'):
            validate_dataset(broken)
        broken = copy.deepcopy(data)
        case = broken['cases'][1]
        next(p for p in case['phases'] if p['kind'] == 'query')['message'] += ' extra hint'
        with self.assertRaisesRegex(ValueError, 'matched'):
            validate_dataset(broken)
    def test_absent_artifact_requires_observed_scope_and_rejects_an_actual_file(self):
        case = {'dimension': 'reuse'}
        rule = {'id': 'no_unsupported_file', 'type': 'artifact_absent', 'phase': 'act', 'path': 'out.json'}
        phase = {'status': 'completed', 'response': '{"ack":true}', 'artifacts': [], 'artifact_scope': ['out.json']}
        self.assertTrue(evaluate_assertion(case, rule, phase)['passed'])
        phase['artifact_scope'] = []
        self.assertIsNone(evaluate_assertion(case, rule, phase)['passed'])
        phase.update(artifact_scope=['out.json'], artifacts=[{'path': 'out.json', 'bytes': 2, 'json': {}}])
        self.assertFalse(evaluate_assertion(case, rule, phase)['passed'])
    def test_episode_generation_has_matched_probes_and_withheld_target_evidence(self):
        module = importlib.import_module('kylin_memory_bench.episodes')
        data = module.generate_episodes(seed=7, split='test', per_dimension=1, interference_sessions=4)
        validate_dataset(data)
        self.assertEqual(len(data['cases']), 12)
        groups = {}
        for case in data['cases']:
            spec = case['intervention']
            groups.setdefault(spec['pair_id'], {})[spec['arm']] = case
            request = adapter_request(case, case['phases'][-1], session_id='fresh', workspace='work')
            self.assertNotIn('intervention', request)
        self.assertEqual(len(groups), 6)
        for arms in groups.values():
            provided, withheld = arms['provided'], arms['withheld']
            self.assertEqual(provided['intervention']['objective'], withheld['intervention']['objective'])
            self.assertEqual([p['id'] for p in provided['phases']], [p['id'] for p in withheld['phases']])
            for one, two in zip(provided['phases'], withheld['phases']):
                if one['kind'] in ('query', 'action'):
                    self.assertEqual(one['message'], two['message'])
            expected = provided['intervention']['objective']['expected']
            values = list(expected.values()) if isinstance(expected, dict) else [expected]
            for value in values:
                self.assertTrue(any(value in p['message'] for p in provided['phases']))
                self.assertFalse(any(value in p['message'] for p in withheld['phases']))
        self.assertEqual(digest(data), digest(module.generate_episodes(7, 'test', 1, 4)))
    def test_known_correct_control_does_not_resurrect_a_delayed_old_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'memory.json'
            request = {'workspace': tmp}
            for version, value in [(1, 'OLD'), (3, 'CURRENT'), (1, 'OLD')]:
                request['message'] = write_message([fact('project', 'path', value, revision=version)])
                respond(request, state, 'perfect')
            request['message'] = block('MEMORY_QUERY', {'subject': 'project', 'key': 'path'})
            self.assertEqual(respond(request, state, 'perfect'), '{"answer": "CURRENT"}')
