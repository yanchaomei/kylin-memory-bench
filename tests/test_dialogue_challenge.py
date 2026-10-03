import copy
import importlib.util
import io
import json
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from kylin_memory_bench.dataset import generate
from kylin_memory_bench.model import DIMENSIONS, adapter_request, digest, validate_dataset
from kylin_memory_bench.scoring import evaluate_assertion


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'generate_dialogue_challenge.py'
DATA = ROOT / 'data' / 'dialogue-24.json'


class DialogueChallengeTests(unittest.TestCase):
    def generator(self):
        self.assertTrue(SCRIPT.is_file(), '自然语言挑战生成脚本尚未实现')
        spec = importlib.util.spec_from_file_location('dialogue_challenge', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_default_seed_and_six_dimensions(self):
        module = self.generator()
        data = module.generate_dialogue()
        validate_dataset(data)
        self.assertEqual(module.DEFAULT_SEED, 20261003)
        self.assertEqual(data['seed'], module.DEFAULT_SEED)
        self.assertEqual(len(data['cases']), 24)
        self.assertEqual(Counter(c['dimension'] for c in data['cases']),
                         Counter({d: 4 for d in DIMENSIONS}))

    def test_determinism_and_seed_changes(self):
        module = self.generator()
        self.assertEqual(module.generate_dialogue(7), module.generate_dialogue(7))
        self.assertNotEqual(digest(module.generate_dialogue(7)),
                            digest(module.generate_dialogue(8)))

    def test_synthetic_provenance_and_separate_identity(self):
        module = self.generator()
        data = module.generate_dialogue(7)
        self.assertEqual(data['schema'], generate(7, 4)['schema'])
        self.assertEqual(data['dataset_id'], 'kmb-dialogue-7-4')
        self.assertEqual(data['provenance']['kind'], 'programmatic_synthetic')
        self.assertIs(data['provenance']['human_gold'], False)
        self.assertEqual(data['provenance']['source_dataset_id'], 'kmb-core-7-4')
        self.assertTrue(all(c['synthetic'] is True for c in data['cases']))

    def test_calls_original_generator_without_mutating_it(self):
        module = self.generator()
        source = generate(7, 4)
        before = copy.deepcopy(source)
        with patch.object(module, 'generate', return_value=source) as base:
            module.generate_dialogue(7)
        base.assert_called_once_with(7, 4)
        self.assertEqual(source, before)

    def test_preserves_fact_truth_assertions_and_phase_contract(self):
        module = self.generator()
        for seed in (7, 20261003, -19):
            source = generate(seed, 4)
            rewritten = module.generate_dialogue(seed)
            for original, case in zip(source['cases'], rewritten['cases']):
                with self.subTest(seed=seed, case=case['id']):
                    for key in ('id', 'dimension', 'stratum', 'synthetic', 'assertions'):
                        self.assertEqual(case[key], original[key])
                    mapping = {}
                    for old, new in zip(original['facts'], case['facts']):
                        mapping.setdefault(old['subject'], new['subject'])
                        self.assertEqual(mapping[old['subject']], new['subject'])
                        self.assertEqual({k: v for k, v in old.items() if k != 'subject'},
                                         {k: v for k, v in new.items() if k != 'subject'})
                    self.assertEqual(len(set(mapping.values())), len(mapping))
                    self.assertEqual(len(case['facts']), len(original['facts']))
                    self.assertEqual(len(case['phases']), len(original['phases']))
                    for old, new in zip(original['phases'], case['phases']):
                        self.assertEqual({k: v for k, v in old.items() if k != 'message'},
                                         {k: v for k, v in new.items() if k != 'message'})
                        self.assertNotEqual(old['message'], new['message'])

    def test_messages_are_natural_language_not_fact_json(self):
        data = self.generator().generate_dialogue()
        for case in data['cases']:
            for phase in case['phases']:
                with self.subTest(case=case['id'], phase=phase['id']):
                    text = phase['message']
                    self.assertRegex(text, r'[\u4e00-\u9fff]')
                    for marker in ('MEMORY_INPUT', 'MEMORY_QUERY', 'MEMORY_ACTION',
                                   '"subject"', '"value"', '"policy"', '"revision"',
                                   'policy=', 'revision', 'session_only'):
                        self.assertNotIn(marker, text)

    def test_query_and_action_requests_never_leak_values(self):
        data = self.generator().generate_dialogue()
        for case in data['cases']:
            values = [f['value'] for f in case['facts']]
            for phase in case['phases']:
                if phase['kind'] not in ('query', 'action', 'distract'):
                    continue
                request = adapter_request(case, phase, session_id='fresh', workspace='/tmp/task')
                self.assertEqual(set(request), {'schema', 'case_id', 'phase_id', 'kind',
                                               'session_id', 'message', 'workspace'})
                text = json.dumps(request, ensure_ascii=False)
                for value in values:
                    with self.subTest(case=case['id'], phase=phase['id'], value=value):
                        self.assertNotIn(value, text)
                self.assertNotIn('facts', request)
                self.assertNotIn('assertions', request)

    def test_every_fact_is_explicitly_grounded_in_the_right_message(self):
        data = self.generator().generate_dialogue()
        for case in data['cases']:
            learn = next(p['message'] for p in case['phases'] if p['id'] == 'learn')
            for fact in case['facts']:
                pid = 'change' if fact['revision'] == 2 else 'learn'
                message = next(p['message'] for p in case['phases'] if p['id'] == pid)
                with self.subTest(case=case['id'], revision=fact['revision']):
                    self.assertIn(fact['subject'], message)
                    self.assertIn(fact['value'], message)
                    if fact['revision'] == 2:
                        self.assertNotIn(fact['value'], learn)
            for assertion in case['assertions']:
                if 'expected' not in assertion:
                    continue
                expected = assertion['expected']
                expected = list(expected.values()) if isinstance(expected, dict) else [expected]
                retained = [f['value'] for f in case['facts'] if f['policy'] == 'retain']
                self.assertTrue(all(value in retained for value in expected))

    def test_subjects_are_consistent_and_queries_identify_the_requested_field(self):
        module = self.generator()
        labels = {'deployment_path': '部署目录', 'export_format': '导出格式标识',
                  'handover_code': '交接编号'}
        for original, case in zip(generate(7, 4)['cases'], module.generate_dialogue(7)['cases']):
            old_subjects = {f['subject'] for f in original['facts']}
            for phase in case['phases']:
                for old in old_subjects:
                    self.assertNotIn(old, phase['message'])
                if phase['kind'] == 'query':
                    if phase['id'] == 'allowed' or (case['dimension'] == 'discrimination'
                                                    and phase['id'] == 'probe2'):
                        target = case['facts'][1]
                    else:
                        target = case['facts'][-1] if case['dimension'] == 'retrieval' else case['facts'][0]
                    self.assertIn(target['subject'], phase['message'])
                    self.assertIn(labels[target['key']], phase['message'])
                    self.assertIn('answer', phase['message'])
                    self.assertIn('null', phase['message'])
                if phase['kind'] == 'action':
                    self.assertIn(case['facts'][0]['subject'], phase['message'])

    def test_discrimination_has_distinct_and_near_named_projects(self):
        cases = [c for c in self.generator().generate_dialogue()['cases']
                 if c['dimension'] == 'discrimination']
        for index, case in enumerate(cases):
            left, right = [f['subject'] for f in case['facts']]
            self.assertNotEqual(left, right)
            if index < 2:
                self.assertNotEqual(left.split('-')[0], right.split('-')[0])
            else:
                self.assertEqual(left.split('-')[0], right.split('-')[0])

    def test_boundary_covers_four_policies_and_positive_controls(self):
        cases = [c for c in self.generator().generate_dialogue()['cases']
                 if c['dimension'] == 'boundary']
        self.assertEqual({c['stratum'] for c in cases},
                         {'session_only', 'sensitive', 'risk', 'noise'})
        for case in cases:
            learn = case['phases'][0]['message']
            self.assertIn('不要写入长期记忆', learn)
            self.assertIn('以后也不要复用', learn)
            self.assertIn('请保存到长期记忆', learn)
            forbidden, allowed = case['facts']
            self.assertNotEqual(forbidden['subject'], allowed['subject'])
            self.assertEqual(allowed['policy'], 'retain')
            memory_rules = [r for r in case['assertions'] if r['type'] == 'memory_absent']
            self.assertEqual({r['phase'] for r in memory_rules}, {p['id'] for p in case['phases']})
            negative = next(r for r in case['assertions'] if r['type'] == 'response_absent')
            self.assertTrue(negative['require_abstention'])
            self.assertEqual(negative['forbidden'], [forbidden['value']])
            positive = next(r for r in case['assertions'] if r['type'] == 'response_value')
            self.assertEqual(positive['expected'], allowed['value'])

    def test_boundary_reason_is_specific_to_the_policy(self):
        cues = {'session_only': '本次会话', 'sensitive': '敏感', 'risk': '未经核实',
                'noise': '闲聊'}
        for case in self.generator().generate_dialogue()['cases']:
            if case['dimension'] == 'boundary':
                self.assertIn(cues[case['stratum']], case['phases'][0]['message'])

    def test_reuse_requires_an_actual_file_without_prefilled_answers(self):
        for case in self.generator().generate_dialogue()['cases']:
            if case['dimension'] != 'reuse':
                continue
            action = case['phases'][-1]['message']
            for text in ('handover.json', 'deployment_path', 'handover_code', '实际创建', '不创建'):
                self.assertIn(text, action)
            rule = case['assertions'][0]
            claim = evaluate_assertion(case, rule, {'status': 'completed', 'response': '{"ack":true}'})
            self.assertIs(claim['passed'], False)
            artifact = {'status': 'completed', 'artifacts': [
                {'path': rule['path'], 'json': rule['expected'], 'fresh': True}]}
            self.assertIs(evaluate_assertion(case, rule, artifact)['passed'], True)

    def test_scoring_still_detects_stale_updates_and_entity_confusion(self):
        for case in self.generator().generate_dialogue()['cases']:
            if case['dimension'] not in ('update', 'discrimination', 'retrieval'):
                continue
            for rule in case['assertions']:
                right = {'status': 'completed', 'response': json.dumps({'answer': rule['expected']})}
                wrong = {'status': 'completed', 'response': json.dumps({'answer': rule['alternatives'][0]})}
                self.assertIs(evaluate_assertion(case, rule, right)['passed'], True)
                outcome = 'stale_update' if case['dimension'] == 'update' else 'confusion'
                self.assertEqual(evaluate_assertion(case, rule, wrong)['outcome'], outcome)

    def test_boundary_scoring_needs_observable_storage_and_abstention(self):
        for case in self.generator().generate_dialogue()['cases']:
            if case['dimension'] != 'boundary':
                continue
            for rule in case['assertions']:
                if rule['type'] == 'memory_absent':
                    unobserved = {'status': 'completed'}
                    self.assertIsNone(evaluate_assertion(case, rule, unobserved)['passed'])
                    clean = {'status': 'completed', 'memory_snapshot': {
                        'observable': True, 'complete': True, 'files': []}}
                    self.assertIs(evaluate_assertion(case, rule, clean)['passed'], True)
                    clean['memory_snapshot']['files'] = [{'path': 'MEMORY.md', 'text': rule['forbidden'][0]}]
                    self.assertIs(evaluate_assertion(case, rule, clean)['passed'], False)
                if rule['type'] == 'response_absent':
                    unknown = {'status': 'completed', 'response': '{"answer":null}'}
                    self.assertIs(evaluate_assertion(case, rule, unknown)['passed'], True)
                    leak = {'status': 'completed', 'response': json.dumps({'answer': None, 'extra': rule['forbidden'][0]})}
                    self.assertIs(evaluate_assertion(case, rule, leak)['passed'], False)

    def test_english_record_has_a_chinese_query(self):
        found = False
        for case in self.generator().generate_dialogue()['cases']:
            learn = case['phases'][0]['message']
            if 'For ' in learn:
                found = True
                for phase in case['phases']:
                    if phase['kind'] == 'query':
                        self.assertRegex(phase['message'], r'[\u4e00-\u9fff]')
        self.assertTrue(found, '应包含少量英文登记、中文查询场景')

    def test_cli_default_destination_and_deterministic_serialization(self):
        module = self.generator()
        self.assertEqual(module.DEFAULT_OUTPUT, DATA)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'dialogue-24.json'
            stdout = io.StringIO()
            with patch.object(module, 'DEFAULT_OUTPUT', output), redirect_stdout(stdout):
                self.assertEqual(module.main([]), 0)
            raw = output.read_bytes()
            data = json.loads(raw)
            self.assertEqual(data, module.generate_dialogue())
            report = json.loads(stdout.getvalue())
            self.assertEqual(report['sha256'], digest(data))
            self.assertEqual(report['cases'], 24)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(['--seed', str(module.DEFAULT_SEED), '--out', str(output)]), 0)
            self.assertEqual(output.read_bytes(), raw)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(['--seed', '8', '--out', str(output)]), 0)
            self.assertEqual(json.loads(output.read_bytes()), module.generate_dialogue(8))

    def test_checked_in_dataset_matches_default_generator(self):
        module = self.generator()
        self.assertTrue(DATA.is_file(), '默认的 24 条自然语言数据集尚未生成')
        raw = DATA.read_bytes()
        data = json.loads(raw)
        self.assertEqual(data, module.generate_dialogue())
        self.assertEqual(raw, (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
                               + '\n').encode('utf8'))


if __name__ == '__main__':
    unittest.main()
