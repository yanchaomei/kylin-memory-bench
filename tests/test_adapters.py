import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from kylin_memory_bench.adapters import Adapter, parse_response, validate_config


class AdapterTests(unittest.TestCase):
    def test_native_hermes_footer_is_removed_without_extracting_answer_from_logs(self):
        answer, meta = parse_response('hermes', '{"answer":"x"}\n\nsession_id: fresh_001\n')
        self.assertEqual(answer, '{"answer":"x"}')
        self.assertEqual(meta['native_session_id'], 'fresh_001')

    def test_hermes_known_stream_banner_is_transport_not_an_answer(self):
        text = '\u256d\u2500 \u2695 Hermes ' + '\u2500'*12 + '\u256e\r\n{"answer":"x"}\r\n\r\nsession_id: fresh_002\r\n'
        answer, meta = parse_response('hermes', text)
        self.assertEqual(answer, '{"answer":"x"}')
        self.assertEqual(meta['native_session_id'], 'fresh_002')
        answer, _ = parse_response('hermes', 'warning: wrong protocol\n{"answer":"x"}\nsession_id: fresh_003\n')
        self.assertTrue(answer.startswith('warning:'))

    def test_openclaw_payload_and_error_envelopes(self):
        self.assertEqual(parse_response('openclaw', '{"payloads":[{"text":"{}"}]}')[0], '{}')
        with self.assertRaises(ValueError):
            parse_response('openclaw', '{"ok":false,"result":{"payloads":[{"text":"{}"}]}}')
        with self.assertRaises(ValueError):
            parse_response('openclaw', '{"payloads":[{"text":"HTTP 403 forbidden: Request not allowed"}],"meta":{"agentMeta":{"lastCallUsage":{"total":0}}}}')

    def test_hermes_copies_only_selected_provider_env_and_no_personal_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'; source.mkdir()
            (source / 'auth.json').write_text('{}')
            (source / '.env').write_text('ANTHROPIC_API_KEY="synthetic-test-only"\nHERMES_GATEWAY_TOKEN=do-not-copy\n')
            (source / 'memories').mkdir()
            (source / 'memories/MEMORY.md').write_text('private-personal-info')
            config = {'name': 'test', 'adapter': 'hermes', 'provider': 'anthropic', 'model': 'test', 'credential_home': str(source)}
            adapter = Adapter(config, root / 'profile', root / 'work', 'python3')
            self.assertEqual(adapter.env.get('ANTHROPIC_API_KEY'), 'synthetic-test-only')
            self.assertFalse((root / 'profile/memories/MEMORY.md').exists())
            self.assertFalse((root / 'profile/.env').exists())

    def test_no_home_override_in_extension_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                Adapter({'name': 'test', 'adapter': 'json-command', 'env': {'HOME': '/tmp/fake'}}, Path(tmp) / 'p', Path(tmp) / 'w', 'python3')

    def test_openclaw_api_uses_environment_reference_without_existing_account(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'KMB_TEST_API_KEY': 'synthetic-api-only-key'}):
            root = Path(tmp)
            config = {'name': 'test', 'adapter': 'openclaw', 'model': 'gpt-6-sol',
                      'base_url': 'http://127.0.0.1:32123/v1', 'api_key_env': 'KMB_TEST_API_KEY', 'api_mode': 'responses',
                      'credential_home': str(root / 'missing-account')}
            adapter = Adapter(config, root / 'p', root / 'w', 'python3')
            text = (root / 'p/openclaw.json').read_text()
            selected = json.loads(text)
            self.assertEqual(selected['models']['providers']['kmb-api']['api'], 'openai-responses')
            self.assertIn('${KMB_TEST_API_KEY}', text)
            self.assertNotIn('synthetic-api-only-key', text)
            self.assertEqual(selected['agents']['defaults']['model']['primary'], 'kmb-api/gpt-6-sol')
            self.assertFalse((root / 'p/agents/main/agent/auth-profiles.json').exists())
            self.assertEqual(selected['agents']['list'][0]['skills'], [])
            sessions = root / 'p/agents/main/sessions'; sessions.mkdir(parents=True)
            (sessions / 'sessions.json').write_text('{"history":"previous conversation"}')
            (root / 'w/MEMORY.md').write_text('durable fact')
            adapter.prepare_phase()
            self.assertFalse(sessions.exists())
            self.assertEqual((root / 'w/MEMORY.md').read_text(), 'durable fact')

    def test_model_timeout_envelope_is_not_a_successful_generation(self):
        with self.assertRaises(ValueError):
            parse_response('openclaw', '{"payloads":[{"text":"LLM request timed out."}],"meta":{"agentMeta":{"lastCallUsage":{"total":0}}}}')

    def test_hermes_api_uses_custom_responses_and_no_oauth_copy(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'KMB_TEST_API_KEY': 'synthetic-api-only-key'}):
            root = Path(tmp)
            config = {'name': 'test', 'adapter': 'hermes', 'model': 'gpt-6-sol',
                      'base_url': 'http://127.0.0.1:32123/v1', 'api_key_env': 'KMB_TEST_API_KEY', 'api_mode': 'responses',
                      'credential_home': str(root / 'missing-account')}
            adapter = Adapter(config, root / 'p', root / 'w', 'python3')
            text = (root / 'p/config.yaml').read_text()
            selected = json.loads(text)
            self.assertEqual(selected['model']['provider'], 'custom')
            self.assertEqual(selected['model']['api_mode'], 'codex_responses')
            self.assertEqual(adapter.env['OPENAI_API_KEY'], 'synthetic-api-only-key')
            self.assertNotIn('synthetic-api-only-key', text)
            self.assertFalse((root / 'p/auth.json').exists())
            request = {'message': '{}', 'session_id': 'fresh'}
            command = adapter.command(request)
            self.assertNotIn('--provider', command)

    def test_api_credential_must_be_present_without_printing_its_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, 'credential environment'):
                Adapter({'name': 'test', 'adapter': 'hermes', 'model': 'test', 'base_url': 'http://127.0.0.1/v1',
                         'api_key_env': 'KMB_INTENTIONALLY_MISSING_KEY'}, root / 'p', root / 'w', 'python3')

    def test_reasoning_setting_is_explicit_in_both_native_frameworks(self):
        for effort in ('off', 'medium'):
            for kind in ('openclaw', 'hermes'):
                with self.subTest(effort=effort, kind=kind), tempfile.TemporaryDirectory() as tmp, patch.dict(
                        'os.environ', {'KMB_TEST_API_KEY': 'synthetic-api-only-key'}):
                    root = Path(tmp)
                    config = {'name': 'test', 'adapter': kind, 'model': 'gpt-6-sol',
                              'base_url': 'https://example.invalid/v1', 'api_key_env': 'KMB_TEST_API_KEY',
                              'api_mode': 'responses', 'reasoning_effort': effort}
                    adapter = Adapter(config, root / 'p', root / 'w', 'python3')
                    if kind == 'openclaw':
                        command = adapter.command({'message': '{}', 'session_id': 'fresh'})
                        self.assertEqual(command[command.index('--thinking') + 1], effort)
                    else:
                        selected = json.loads((root / 'p/config.yaml').read_text())
                        self.assertEqual(selected.get('agent', {}).get('reasoning_effort'),
                                         'none' if effort == 'off' else effort)

    def test_invalid_reasoning_setting_is_rejected(self):
        for effort in ('turbo', None, 1):
            with self.subTest(effort=effort), self.assertRaisesRegex(ValueError, 'reasoning_effort'):
                validate_config({'name': 'test', 'adapter': 'hermes', 'reasoning_effort': effort})

    def test_hermes_trace_includes_native_model_and_usage_without_profile_secrets(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'KMB_TEST_API_KEY': 'synthetic-api-only-key'}):
            root = Path(tmp)
            adapter = Adapter({'name': 'test', 'adapter': 'hermes', 'model': 'test',
                               'base_url': 'https://example.invalid/v1', 'api_key_env': 'KMB_TEST_API_KEY'},
                              root / 'p', root / 'w', 'python3')
            with sqlite3.connect(root / 'p/state.db') as db:
                db.execute('CREATE TABLE messages (id INTEGER, session_id TEXT, role TEXT, content TEXT, tool_name TEXT, tool_calls TEXT, tool_call_id TEXT)')
                db.execute('CREATE TABLE sessions (id TEXT, model TEXT, input_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER, model_config TEXT)')
                db.execute('INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)',
                           ('fresh', 'actual-native-model', 12, 3, 0, 'synthetic-api-only-key'))
            trace = adapter.trace({'session_id': 'fresh'}, {'native_session_id': 'fresh'})
            text = json.dumps(trace)
            self.assertTrue(trace['observable'])
            self.assertTrue(trace['complete'])
            self.assertIn('actual-native-model', text)
            self.assertNotIn('synthetic-api-only-key', text)


if __name__ == '__main__':
    unittest.main()
