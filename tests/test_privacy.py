import unittest

from kylin_memory_bench.privacy import redact, secret_values


class PrivacyTests(unittest.TestCase):
    def test_actual_provider_secrets_and_debug_prefixes_are_redacted(self):
        known = secret_values({'profiles': {'demo': {'key': 'only-a-synthetic-secret', 'provider': 'test'}}})
        value = redact('bad only-a-synthetic-secret\nToken prefix: private-fragment...\nKMB_FAKE_SENSITIVE_123', known)
        self.assertNotIn('only-a-synthetic-secret', value)
        self.assertNotIn('private-fragment', value)
        self.assertIn('KMB_FAKE_SENSITIVE_123', value)


if __name__ == '__main__':
    unittest.main()
