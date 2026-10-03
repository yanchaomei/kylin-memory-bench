"""Native CLI adapters and a small JSON-stdio extension contract."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

from .evidence import confined_file, snapshot_files, snapshot_sqlite, write_json
from .privacy import secret_values
from .model import parse_json

HERE = Path(__file__).resolve().parent.parent


def private_copy(source: Path, target: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise ValueError('credential source must be a regular file')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile(source, target)
    target.chmod(0o600)


def parse_response(adapter: str, stdout: str) -> tuple[str, dict]:
    if adapter == 'hermes':
        stdout = stdout.replace('\r\n', '\n')
        match = re.search(r'\nsession_id: ([A-Za-z0-9_.:-]+)\s*$', stdout)
        if not match:
            raise ValueError('Hermes session footer missing')
        text = stdout[:match.start()].strip()
        text = re.sub(r'^\u256d\u2500 \u2695(?:\ufe0f)? Hermes \u2500+\u256e\n', '', text, count=1)
        return text, {'native_session_id': match.group(1)}
    obj = parse_json(stdout)
    if not isinstance(obj, dict):
        raise ValueError('native response envelope must be an object')
    if adapter == 'openclaw':
        if obj.get('status') == 'error' or obj.get('ok') is False:
            raise ValueError('OpenClaw returned an error envelope')
        result = obj.get('result', obj)
        if not isinstance(result, dict):
            raise ValueError('OpenClaw result must be an object')
        payloads = result.get('payloads', [])
        if not isinstance(payloads, list) or not all(isinstance(p, dict) for p in payloads):
            raise ValueError('OpenClaw payloads must be an array of objects')
        texts = [p['text'] for p in payloads if isinstance(p.get('text'), str)]
        if not texts:
            raise ValueError('OpenClaw returned no text payload')
        meta = result.get('meta') or {}
        if not isinstance(meta, dict):
            raise ValueError('OpenClaw metadata must be an object')
        agent_meta = meta.get('agentMeta', {})
        if not isinstance(agent_meta, dict):
            raise ValueError('OpenClaw agent metadata must be an object')
        usage = agent_meta.get('lastCallUsage') or {}
        if not isinstance(usage, dict):
            raise ValueError('OpenClaw usage metadata must be an object')
        if (usage.get('total') == 0
                and any(re.match(r'^(HTTP [45]\d\d|OAuth|Error:|LLM request timed out)', t) for t in texts)):
            raise ValueError('OpenClaw model service failed before generation')
        return '\n'.join(texts), {'meta': meta, 'native_session_id': agent_meta.get('sessionId')}
    if not isinstance(obj, dict) or not isinstance(obj.get('response'), str):
        raise ValueError('JSON adapter must return a string response field')
    return obj['response'], {'native_session_id': obj.get('session_id')}


class Adapter:
    def __init__(self, config: dict, profile: Path, workspace: Path, python: str):
        self.config = config
        self.kind = config['adapter']
        self.profile = profile
        self.workspace = workspace
        self.python = python
        self.env = os.environ.copy()
        self.secrets = {v for k, v in self.env.items() if re.search('KEY|TOKEN|SECRET|PASSWORD', k) and len(v) >= 8}
        self.env['PYTHONPATH'] = str(HERE)
        self.env['NO_COLOR'] = '1'
        self.memory_root = profile
        self.patterns = []
        profile.mkdir(parents=True, mode=0o700)
        workspace.mkdir(parents=True, mode=0o700)
        api = bool(config.get('base_url'))
        if api:
            key_name = config.get('api_key_env', '')
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key_name) or not self.env.get(key_name):
                raise ValueError('API credential environment is missing or invalid')
            self.secrets.add(self.env[key_name])
        if self.kind == 'fixture':
            self.patterns = ['memory.json']
        elif self.kind == 'openclaw':
            source = Path(config.get('credential_home', '~/.openclaw')).expanduser()
            if not api:
                private_copy(source / 'agents/main/agent/auth-profiles.json', profile / 'agents/main/agent/auth-profiles.json')
                self.secrets.update(secret_values(json.loads((profile / 'agents/main/agent/auth-profiles.json').read_text())))
            source_config = json.loads((source / 'openclaw.json').read_text()) if not api else {}
            self.secrets.update(secret_values(source_config))
            model = config.get('model', source_config.get('agents', {}).get('defaults', {}).get('model', {}).get('primary'))
            if not isinstance(model, str) or not model:
                raise ValueError('OpenClaw model must be explicit')
            selected = {'agents': {'defaults': {'workspace': str(workspace), 'model': {'primary': model},
                                               'skipBootstrap': True},
                                    'list': [{'id': 'main', 'default': True, 'workspace': str(workspace), 'skills': []}]},
                        'tools': {'allow': ['read', 'write', 'edit', 'memory_search', 'memory_get'],
                                  'fs': {'workspaceOnly': True}},
                        'plugins': {'enabled': False}}
            if source_config.get('auth'):
                selected['auth'] = source_config['auth']
            # Provider settings remain private; channels and personal workspaces are never copied.
            if config.get('copy_provider_config') and source_config.get('models'):
                selected['models'] = source_config['models']
            if api:
                transport = 'openai-responses' if config.get('api_mode', 'chat_completions') == 'responses' else 'openai-completions'
                selected['models'] = {'providers': {'kmb-api': {'baseUrl': config['base_url'],
                    'apiKey': '${' + config['api_key_env'] + '}', 'api': transport,
                    'models': [{'id': model, 'name': model, 'reasoning': True, 'input': ['text'],
                                'contextWindow': config.get('context_tokens', 32768),
                                'maxTokens': config.get('max_output_tokens', 4096)}]}}}
                selected['agents']['defaults']['model']['primary'] = 'kmb-api/' + model
            write_json(profile / 'openclaw.json', selected)
            (profile / 'openclaw.json').chmod(0o600)
            (workspace / 'AGENTS.md').write_text(
                '# Memory workspace\nUse MEMORY.md and memory/*.md for durable notes. '
                'Read the retained notes before answering a fresh-session memory question. '
                'Only retain information whose user policy allows it. Do not infer unknown values.\n', encoding='utf8')
            self.env.update(OPENCLAW_STATE_DIR=str(profile), OPENCLAW_CONFIG_PATH=str(profile / 'openclaw.json'))
            self.memory_root = workspace
            self.patterns = ['MEMORY.md', 'memory/*.md']
        elif self.kind == 'hermes':
            source = Path(config.get('credential_home', '~/.hermes')).expanduser()
            if not api:
                private_copy(source / 'auth.json', profile / 'auth.json')
                self.secrets.update(secret_values(json.loads((profile / 'auth.json').read_text())))
            model = config.get('model', 'gpt-5.4')
            provider = config.get('provider', 'openai-codex')
            selected = {'model': {'default': model, 'provider': provider},
                        'memory': {'memory_enabled': True, 'user_profile_enabled': True,
                                   'memory_char_limit': 2200, 'user_char_limit': 1375},
                        'terminal': {'backend': 'local', 'cwd': str(workspace)}}
            if 'reasoning_effort' in config:
                effort = config['reasoning_effort']
                selected['agent'] = {'reasoning_effort': 'none' if effort == 'off' else effort}
            if api:
                selected['model'].update(provider='custom', base_url=config['base_url'],
                    api_mode='codex_responses' if config.get('api_mode') == 'responses' else 'chat_completions')
                self.env['OPENAI_API_KEY'] = self.env[config['api_key_env']]
            # JSON is a valid YAML subset; no YAML dependency is needed by the benchmark.
            write_json(profile / 'config.yaml', selected)
            (profile / 'config.yaml').chmod(0o600)
            self.env.update(HERMES_HOME=str(profile), TERMINAL_CWD=str(workspace))
            if not api and provider == 'anthropic' and (source / '.env').is_file():
                allowed = {'ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL'}
                for line in (source / '.env').read_text().splitlines():
                    key, sep, value = line.partition('=')
                    if sep and key.strip() in allowed:
                        pieces = shlex.split(value, comments=True)
                        if len(pieces) == 1:
                            self.env[key.strip()] = pieces[0]
                            if key.strip() == 'ANTHROPIC_API_KEY':
                                self.secrets.add(pieces[0])
            self.patterns = ['memories/MEMORY.md', 'memories/USER.md']
        elif self.kind == 'json-command':
            self.patterns = config.get('memory_patterns', [])
            self.memory_root = workspace if config.get('memory_root') == 'workspace' else profile
            for key, value in config.get('env', {}).items():
                if key in {'HOME', 'CODEX_HOME'}:
                    raise ValueError('framework adapters must not repurpose HOME or CODEX_HOME')
                self.env[key] = str(value).replace('{profile}', str(profile)).replace('{workspace}', str(workspace))
                if re.search('KEY|TOKEN|SECRET|PASSWORD', key) and len(self.env[key]) >= 8:
                    self.secrets.add(self.env[key])
        else:
            raise ValueError('unsupported adapter')

    def memory_snapshot(self) -> dict:
        result = snapshot_files(self.memory_root, self.patterns)
        extra = snapshot_sqlite(self.memory_root, self.config.get('memory_databases', []))
        result['observable'] = result['observable'] or extra['observable']
        result['complete'] = result['complete'] and extra['complete']
        result['files'].extend(extra['files'])
        result['errors'].extend(extra['errors'])
        result['scope'] = {'files': self.patterns, 'databases': extra['scope']}
        return result

    def prepare_phase(self) -> None:
        if self.kind == 'openclaw':
            # This CLI version reuses main's conversation index despite --session-id.
            sessions = confined_file(self.profile, 'agents/main/sessions')
            if sessions.exists():
                shutil.rmtree(sessions)

    def trace(self, request: dict, metadata: dict) -> dict:
        session = metadata.get('native_session_id', request['session_id'])
        if not isinstance(session, str) or not re.fullmatch('[A-Za-z0-9_.:-]+', session):
            return {'observable': False, 'complete': False, 'files': [], 'errors': ['session id unavailable']}
        if self.kind == 'openclaw':
            return snapshot_files(self.profile, [f'agents/main/sessions/{session}.jsonl'])
        if self.kind == 'hermes':
            return snapshot_sqlite(self.profile, [{'path': 'state.db',
                'query': 'SELECT role, content, tool_name, tool_calls, tool_call_id FROM messages WHERE session_id = ? ORDER BY id',
                'params': [session]}, {'path': 'state.db',
                'query': 'SELECT model, input_tokens, output_tokens, reasoning_tokens FROM sessions WHERE id = ?',
                'params': [session]}])
        return {'observable': False, 'complete': True, 'files': [], 'scope': [], 'errors': []}

    def command(self, request: dict) -> list[str]:
        c = self.config
        if self.kind == 'fixture':
            return [self.python, '-m', 'kylin_memory_bench.fixture', '--state', str(self.profile / 'memory.json'),
                    '--mode', c.get('mode', 'perfect')]
        if self.kind == 'openclaw':
            return [c.get('executable', 'openclaw'), 'agent', '--local', '--json', '--agent', 'main',
                    '--session-id', request['session_id'], '--message', request['message'],
                    '--thinking', c.get('reasoning_effort', 'off'), '--timeout', str(c.get('timeout', 180))]
        if self.kind == 'hermes':
            provider_args = [] if c.get('base_url') else ['--provider', c.get('provider', 'openai-codex')]
            return [c.get('executable', 'hermes'), 'chat', '-Q', '-q', request['message'], '--source', 'tool',
                    '--model', c.get('model', 'gpt-5.4'), *provider_args,
                    '--toolsets', 'memory,file', '--max-turns', str(c.get('max_turns', 12))]
        command = c.get('command', [])
        if not command or not all(isinstance(a, str) for a in command):
            raise ValueError('JSON command must be a non-empty argv array')
        return [a.replace('{profile}', str(self.profile)).replace('{workspace}', str(self.workspace)) for a in command]


def validate_config(config: dict) -> None:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', config.get('name', '')):
        raise ValueError('agent name must be a safe identifier')
    if config.get('adapter') not in {'fixture', 'openclaw', 'hermes', 'json-command'}:
        raise ValueError('unsupported adapter type')
    if not 1 <= float(config.get('timeout', 180)) <= 3600:
        raise ValueError('timeout must be between 1 and 3600 seconds')
    if any(k in config for k in ('api_key', 'token', 'password')):
        raise ValueError('secrets belong in private framework profiles or environment variables')
    if 'reasoning_effort' in config and config['reasoning_effort'] not in ('off', 'low', 'medium', 'high'):
        raise ValueError('reasoning_effort must be off, low, medium or high')
