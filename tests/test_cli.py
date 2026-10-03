import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from kylin_memory_bench.cli import main


class CliTests(unittest.TestCase):
    def test_generate_validate_and_invalid_dataset_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample.json'
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['generate', '--out', str(path), '--per-dimension', '1']), 0)
                self.assertEqual(main(['validate', str(path)]), 0)
            path.write_text('{"schema":"bad"}')
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['validate', str(path)]), 2)

    def test_standalone_loose_score_is_not_accepted_for_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'score.json'; path.write_text('{}')
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['compare', str(path), '--out', str(Path(tmp) / 'report')]), 2)


if __name__ == '__main__':
    unittest.main()
