import copy
import tempfile
import unittest
from pathlib import Path

from kylin_memory_bench.dataset import generate
from kylin_memory_bench.model import digest
from kylin_memory_bench.reporting import compare_scores, render_report
from kylin_memory_bench.scoring import score_run


def empty_score(name='empty', kind='real'):
    return score_run(generate(42, 1), {'run_id': name, 'agent': name, 'agent_kind': kind,
                                     'environment': {}, 'dataset_sha256': digest(generate(42, 1)), 'cases': []})


class ReportingTests(unittest.TestCase):
    def test_different_datasets_cannot_be_compared(self):
        one = empty_score()
        two = copy.deepcopy(one)
        two['dataset_sha256'] = 'different'
        with self.assertRaises(ValueError):
            compare_scores([one, two])

    def test_fixtures_and_real_agents_cannot_be_ranked_together(self):
        with self.assertRaises(ValueError):
            compare_scores([empty_score('a'), empty_score('b', 'fixture')])

    def test_empty_score_is_zero_success_not_full_retention(self):
        report = compare_scores([empty_score('agent')])
        self.assertEqual(report['agents'][0]['dimensions']['persistence']['success_rate'], 0)
        self.assertEqual(report['agents'][0]['dimensions']['persistence']['coverage'], 0)

    def test_report_is_self_contained_escaped_and_six_dimensional(self):
        score = empty_score()
        score['cases'][0]['assertions'][0]['reason'] = '<script>alert(1)</script>'
        with tempfile.TemporaryDirectory() as tmp:
            render_report([score], Path(tmp))
            html = (Path(tmp) / 'report.html').read_text()
            self.assertNotIn('<script>alert(1)</script>', html)
            self.assertIn('&lt;script&gt;', html)
            self.assertIn('长期保持', html)
            self.assertTrue((Path(tmp) / 'radar.svg').exists())
            self.assertTrue((Path(tmp) / 'metrics.csv').exists())


if __name__ == '__main__':
    unittest.main()
