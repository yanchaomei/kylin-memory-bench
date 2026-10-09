import copy
import importlib
import unittest


def row(pair, arm, attained, safe=True):
    return {'case_id': pair + '-' + arm, 'dimension': 'reuse', 'passed': safe,
            'intervention': {'pair_id': pair, 'arm': arm, 'objective': {'type': 'response_value', 'phase': 'q', 'expected': 'x'}},
            'target_attainment': {'passed': attained}}


class PairedTests(unittest.TestCase):
    def test_correct_abstention_is_not_no_memory_task_success(self):
        summarize = importlib.import_module('kylin_memory_bench.paired').summarize_pairs
        result = summarize([{'run_id': 'one', 'cases': [row('a', 'provided', True), row('a', 'withheld', False)]}])
        self.assertEqual(result['mean_source_gain'], 1.0)
        self.assertEqual(result['withheld_target_rate'], 0.0)
        self.assertEqual(result['withheld_safe_case_rate'], 1.0)

    def test_repeats_cluster_by_pair_and_missing_pairs_are_not_imputed(self):
        summarize = importlib.import_module('kylin_memory_bench.paired').summarize_pairs
        one = {'run_id': 'one', 'cases': [row('a', 'provided', True), row('a', 'withheld', False),
                                        row('b', 'provided', False), row('b', 'withheld', False)]}
        two = copy.deepcopy(one); two['run_id'] = 'two'
        two['cases'][0]['target_attainment']['passed'] = None
        result = summarize([one, two])
        self.assertEqual(result['independent_pairs'], 2)
        self.assertEqual(result['complete_pairs'], 1)
        self.assertEqual(result['complete_pair_coverage'], 0.5)
        self.assertEqual(result['mean_source_gain'], 0.0)
        self.assertEqual(result['total_pair_executions'], 4)
        self.assertIsNone(result['bootstrap_95'])
