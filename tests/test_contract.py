import copy
import json
import tempfile
import unittest
from pathlib import Path

from kylin_memory_bench.dataset import generate
from kylin_memory_bench.model import adapter_request, digest, relative_path, validate_dataset
from kylin_memory_bench.scoring import evaluate_assertion, score_run


class ContractTests(unittest.TestCase):
    def test_seed_is_reproducible_and_all_dimensions_are_present(self):
        data = generate(7, 4)
        self.assertEqual(data, generate(7, 4))
        self.assertNotEqual(digest(data), digest(generate(8, 4)))
        self.assertEqual(len(data['cases']), 24)
        self.assertEqual({c['stratum'] for c in data['cases'] if c['dimension'] == 'boundary'},
                         {'session_only', 'sensitive', 'risk', 'noise'})

    def test_oracles_never_enter_request(self):
        case = generate(7, 1)['cases'][-1]
        req = adapter_request(case, case['phases'][-1], session_id='new', workspace='/tmp/task')
        self.assertEqual(set(req), {'schema', 'case_id', 'phase_id', 'kind', 'session_id', 'message', 'workspace'})
        for item in case['facts']:
            self.assertNotIn(item['value'], json.dumps(req))

    def test_boundary_includes_a_legitimate_retention_control(self):
        case = generate(7, 1)['cases'][4]
        self.assertIn('retain', {f['policy'] for f in case['facts']})
        self.assertIn('response_value', {r['type'] for r in case['assertions']})

    def test_reject_traversal_and_duplicate_cases(self):
        for name in ('../secret', '/etc/passwd', 'a/../../secret', 'a\\b'):
            with self.assertRaises(ValueError):
                relative_path(name)
        data = generate(7, 1)
        data['cases'].append(copy.deepcopy(data['cases'][0]))
        with self.assertRaises(ValueError):
            validate_dataset(data)
        data = generate(7, 1)
        data['cases'][0]['facts'][0]['policy'] = 'unknown'
        with self.assertRaises(ValueError):
            validate_dataset(data)

    def test_stale_and_similar_values_are_distinguishable(self):
        case = generate(7, 1)['cases'][2]
        rule = case['assertions'][0]
        result = evaluate_assertion(case, rule, {'status': 'completed', 'response': json.dumps({'answer': rule['alternatives'][0]})})
        self.assertEqual(result['outcome'], 'stale_update')
        case['dimension'] = 'discrimination'
        self.assertEqual(evaluate_assertion(case, rule, {'status': 'completed', 'response': json.dumps({'answer': rule['alternatives'][0]})})['outcome'], 'confusion')

    def test_completion_claim_does_not_satisfy_artifact(self):
        case = generate(7, 1)['cases'][-1]
        result = evaluate_assertion(case, case['assertions'][0], {'status': 'completed', 'response': 'File created successfully.'})
        self.assertFalse(result['passed'])
        self.assertEqual(result['outcome'], 'incorrect_reuse')

    def test_unobservable_storage_is_not_success(self):
        case = generate(7, 1)['cases'][4]
        result = evaluate_assertion(case, case['assertions'][0], {'status': 'completed', 'response': '{"ack":true}'})
        self.assertIsNone(result['passed'])
        self.assertEqual(result['outcome'], 'storage_unobservable')

    def test_encoded_forbidden_storage_is_detected(self):
        import base64
        case = generate(7, 1)['cases'][4]
        rule = case['assertions'][0]
        value = base64.b64encode(rule['forbidden'][0].encode()).decode()
        phase = {'status': 'completed', 'memory_snapshot': {'observable': True, 'complete': True, 'files': [{'path': 'MEMORY.md', 'text': value}]}}
        self.assertEqual(evaluate_assertion(case, rule, phase)['outcome'], 'incorrect_persistence')

    def test_protocol_errors_have_coverage_cost(self):
        case = generate(7, 1)['cases'][0]
        result = evaluate_assertion(case, case['assertions'][0], {'status': 'completed', 'response': 'I remember it.'})
        self.assertIsNone(result['passed'])
        self.assertEqual(result['outcome'], 'protocol_error')

    def test_score_rejects_duplicate_phase_evidence(self):
        data = generate(7, 1)
        run = {'run_id': 'x', 'agent': 'x', 'agent_kind': 'fixture', 'environment': {}, 'dataset_sha256': digest(data),
               'cases': [{'id': data['cases'][0]['id'], 'phases': [{'phase_id': 'probe1'}, {'phase_id': 'probe1'}]}]}
        with self.assertRaises(ValueError):
            score_run(data, run)

    def test_bool_is_not_a_numeric_memory_match(self):
        case = generate(7, 1)['cases'][0]
        rule = dict(case['assertions'][0], expected=1)
        self.assertFalse(evaluate_assertion(case, rule, {'status': 'completed', 'response': '{"answer":true}'})['passed'])

    def test_duplicate_json_keys_are_not_a_valid_answer(self):
        case = generate(7, 1)['cases'][0]
        expected = json.dumps(case['assertions'][0]['expected'])
        phase = {'status': 'completed', 'response': '{"answer":"wrong","answer":' + expected + '}'}
        self.assertIsNone(evaluate_assertion(case, case['assertions'][0], phase)['passed'])

    def test_import_validation_requires_provenance_and_facts_contract(self):
        data = generate(7, 1)
        del data['provenance']
        with self.assertRaises(ValueError):
            validate_dataset(data)

    def test_setup_failure_is_not_counted_as_memory_omission(self):
        data = generate(7, 1)
        case = data['cases'][0]
        phases = [{'phase_id': p['id'], 'status': 'completed', 'response': '{"answer":null}'} for p in case['phases']]
        phases[0]['status'] = 'failed'
        run = {'run_id': 'setup-failure', 'agent': 'test', 'agent_kind': 'fixture', 'environment': {},
               'dataset_sha256': digest(data), 'cases': [{'id': case['id'], 'phases': phases}]}
        score = score_run(data, run)
        self.assertIsNone(score['cases'][0]['passed'])
        self.assertEqual(score['dimensions']['persistence']['coverage'], 0)

    def test_malformed_phase_and_assertion_shapes_are_rejected(self):
        for key in ('phases', 'assertions'):
            data = generate(7, 1)
            data['cases'][0][key] = [None]
            with self.subTest(field=key), self.assertRaises(ValueError):
                validate_dataset(data)


if __name__ == '__main__':
    unittest.main()
