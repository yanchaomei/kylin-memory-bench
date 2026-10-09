import importlib.util
from pathlib import Path
import unittest


def analysis_module():
    path = Path(__file__).resolve().parents[1] / 'scripts/analyze_study.py'
    spec = importlib.util.spec_from_file_location('kmb_analysis', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReliabilityTests(unittest.TestCase):
    def test_unequal_repeats_do_not_produce_a_paired_system_significance_claim(self):
        from kylin_memory_bench.episodes import generate_episodes
        from kylin_memory_bench.model import digest
        from kylin_memory_bench.scoring import score_run
        m = analysis_module()
        data = generate_episodes(7, 'test', 1, 1)
        scores = [score_run(data, {'run_id': name, 'agent': agent, 'agent_kind': 'fixture',
                                   'environment': {}, 'dataset_sha256': digest(data), 'cases': []})
                  for name, agent in [('a1', 'a'), ('a2', 'a'), ('b1', 'b')]]
        result = m.summarize(scores)
        self.assertFalse(result['system_contrasts'][0]['comparable'])
        self.assertNotIn('operational', result['system_contrasts'][0])
    def test_reliable_success_is_not_agreement_or_at_least_once_success(self):
        m = analysis_module()
        result = m.reliability([{'a': True, 'b': True}, {'a': True, 'b': False}])
        self.assertEqual(result['pass_power'], {'1': 0.75, '2': 0.5})
        failed = m.reliability([{'a': False}, {'a': False}, {'a': False}])
        self.assertEqual(failed['repeat_state_agreement'], 1.0)
        self.assertEqual(failed['all_repeats_success_rate'], 0.0)

    def test_unknown_has_coverage_cost_and_different_case_inventories_are_rejected(self):
        m = analysis_module()
        result = m.reliability([{'a': True}, {'a': None}])
        self.assertEqual(result['scorable_fraction'], 0.5)
        self.assertEqual(result['pass_power'], {'1': 0.5, '2': 0.0})
        with self.assertRaises(ValueError):
            m.reliability([{'a': True}, {'b': True}])

    def test_exact_system_comparison_uses_paired_disagreements(self):
        m = analysis_module()
        result = m.exact_mcnemar({'a': True, 'b': True, 'c': True, 'd': False},
                                 {'a': False, 'b': False, 'c': False, 'd': False})
        self.assertEqual(result['only_first'], 3)
        self.assertEqual(result['only_second'], 0)
        self.assertEqual(result['exact_two_sided_p'], 0.25)
