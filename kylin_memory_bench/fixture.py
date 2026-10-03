"""Explicit calibration fixtures, never labelled as real agents."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evidence import write_json
from .model import relative_path


def payload(message: str, tag: str):
    start = f'\n{tag}\n'
    if start not in message:
        return None
    return json.loads(message.split(start, 1)[1].split(f'\nEND_{tag}', 1)[0])


def respond(request: dict, state_path: Path, mode: str) -> str:
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    incoming = payload(request['message'], 'MEMORY_INPUT')
    query = payload(request['message'], 'MEMORY_QUERY')
    action = payload(request['message'], 'MEMORY_ACTION')
    if incoming is not None:
        for item in incoming:
            key = item['subject'] + ':' + item['key']
            if mode != 'session-only' and (item['policy'] == 'retain' or mode == 'unsafe'):
                if mode != 'stale' or key not in state:
                    state[key] = item['value']
        write_json(state_path, state)
        return '{"ack":true}'
    if query is not None:
        key = query['subject'] + ':' + query['key']
        answer = state.get(key)
        if mode == 'confuse' and state:
            answer = next(iter(state.values()))
        return json.dumps({'answer': answer}, ensure_ascii=False)
    if action is not None:
        values = {key: state.get(action['subject'] + ':' + key) for key in action['keys']}
        if all(v is not None for v in values.values()) and mode != 'claim-only':
            target = Path(request['workspace']) / relative_path(action['path'])
            write_json(target, values)
        return '{"ack":true}'
    return '{"answer":42}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--mode', choices=['perfect', 'session-only', 'stale', 'confuse', 'unsafe', 'claim-only'], required=True)
    args = parser.parse_args()
    request = json.load(sys.stdin)
    print(json.dumps({'response': respond(request, args.state, args.mode)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
