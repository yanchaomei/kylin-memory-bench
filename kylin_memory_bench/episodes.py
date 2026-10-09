"""Matched source-availability interventions over incremental memory episodes."""
from __future__ import annotations

import copy
import hashlib
import re

from .dataset import block, fact, generate, phase, positive, token, write_message
from .model import canonical, relative_path, validate_dataset


def validate_episode_pairs(data: dict) -> None:
    groups = {}
    for case in data['cases']:
        spec = case.get('intervention', {})
        if not isinstance(spec, dict) or spec.get('arm') not in ('provided', 'withheld'):
            raise ValueError('episode pair needs an explicit provided/withheld arm')
        pair_id = spec.get('pair_id', '')
        if not isinstance(pair_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', pair_id):
            raise ValueError('invalid episode pair id')
        if spec.get('split') not in ('development', 'test'):
            raise ValueError('episode split invalid')
        if type(spec.get('interference_sessions')) is not int or not 1 <= spec['interference_sessions'] <= 64:
            raise ValueError('episode interference_sessions invalid')
        objective = spec.get('objective')
        if not isinstance(objective, dict) or objective.get('type') not in ('response_value', 'artifact_json') or 'expected' not in objective:
            raise ValueError('episode objective must be a positive response or artifact oracle')
        if not objective.get('id') or objective.get('phase') not in {p['id'] for p in case['phases']}:
            raise ValueError('episode objective phase missing')
        if objective.get('field', 'answer') != 'answer':
            raise ValueError('episode objective uses the answer field')
        if objective['type'] == 'artifact_json':
            relative_path(objective['path'])
            if not any(r['phase'] == objective['phase'] and r.get('path') == objective['path']
                       and r['type'] in ('artifact_json', 'artifact_absent') for r in case['assertions']):
                raise ValueError('episode artifact objective needs a declared observation')
        arms = groups.setdefault(pair_id, {})
        if spec['arm'] in arms:
            raise ValueError('episode pair has duplicate arms')
        arms[spec['arm']] = case
    for arms in groups.values():
        if set(arms) != {'provided', 'withheld'}:
            raise ValueError('episode pair is incomplete')
        one, two = arms['provided'], arms['withheld']
        if one['dimension'] != two['dimension'] or any(
                canonical(one['intervention'][k]) != canonical(two['intervention'][k])
                for k in ('objective', 'split', 'interference_sessions')):
            raise ValueError('episode pair conditions or objective differ')
        if [(p['id'], p['kind']) for p in one['phases']] != [(p['id'], p['kind']) for p in two['phases']]:
            raise ValueError('episode matched phase inventory differs')
        if any(a['message'] != b['message'] for a, b in zip(one['phases'], two['phases'])
               if a['kind'] in ('query', 'action')):
            raise ValueError('episode matched probes differ')
    if len(data['cases']) % 12:
        raise ValueError('registered episode pair inventory is incomplete')
    first = data['cases'][0]['intervention']
    expected = _build_episodes(data['seed'], first['split'], len(data['cases']) // 12,
                               first['interference_sessions'])
    if canonical(data) != canonical(expected):
        raise ValueError('registered episode pairing differs from frozen generator parameters')


def _build_episodes(seed: int, split: str, per_dimension: int, interference_sessions: int) -> dict:
    if split not in ('development', 'test'):
        raise ValueError('split must be development or test')
    if type(interference_sessions) is not int or not 1 <= interference_sessions <= 64:
        raise ValueError('interference_sessions must be between 1 and 64')
    world_seed = int(hashlib.sha256(f'{seed}:{split}'.encode()).hexdigest()[:12], 16)
    data = generate(world_seed, per_dimension)
    cases = []
    for index, original in enumerate(data['cases']):
        base = copy.deepcopy(original)
        axis = base['dimension']
        if axis == 'discrimination':
            alternate = 'ALTERNATIVE_' + token(world_seed, axis, index, 'independent-value')
            base['facts'][1]['value'] = alternate
            base['assertions'][0]['alternatives'] = [alternate]
            base['assertions'][1]['expected'] = alternate
        inputs = {'learn': base['facts'][:1] if axis == 'update' else list(base['facts'])}
        if axis == 'reuse':
            initial = copy.deepcopy(base['assertions'][0]['expected'])
            subject = base['facts'][0]['subject']
            action = {'subject': subject, 'keys': ['deployment_path', 'handover_code'], 'path': 'checkpoint.json'}
            message = ('依据已保留的交接信息，在当前目录实际创建 checkpoint.json，包含 deployment_path 和 handover_code。'
                       '缺少可靠资料则不创建。只回复 JSON {"ack":true}。' + block('MEMORY_ACTION', action))
            base['phases'].insert(1, phase('checkpoint', 'action', 'checkpoint', message))
            updated = fact(subject, 'handover_code', 'FEEDBACK_' + token(world_seed, axis, index, 'feedback'), revision=2)
            base['facts'].append(updated)
            inputs['feedback'] = [updated]
            base['phases'].insert(len(base['phases']) - 1,
                                  phase('feedback', 'update', 'feedback', write_message([updated])))
            base['assertions'][0]['expected']['handover_code'] = updated['value']
            base['assertions'].insert(0, {'id': 'first_action_artifact', 'phase': 'checkpoint',
                                          'type': 'artifact_json', 'path': 'checkpoint.json', 'expected': initial})
        if axis == 'update':
            inputs['change'] = base['facts'][1:]
            first = base['facts'][0]
            latest = fact(first['subject'], first['key'], 'LATEST_' + token(world_seed, axis, index, 'v3'), revision=3)
            base['facts'].append(latest)
            probe_index = next(i for i, p in enumerate(base['phases']) if p['id'] == 'probe')
            base['phases'][probe_index:probe_index] = [
                phase('latest', 'update', 'latest', write_message([latest])),
                phase('delayed', 'update', 'delayed', write_message([first]))]
            inputs.update(latest=[latest], delayed=[first])
            base['assertions'] = [positive('probe', latest['value'],
                                           alternatives=[f['value'] for f in base['facts'][:-1]])]
        gaps = []
        for n in range(interference_sessions):
            pid = 'gap' if n == 0 else f'gap-{n:02d}'
            noise = fact(f'并行办公事项-{token(world_seed, axis, index, str(n))[:8]}',
                         'handover_code', 'DISTRACTOR_' + token(world_seed, axis, index, f'gap-{n}'))
            base['facts'].append(noise)
            inputs[pid] = [noise]
            gaps.append(phase(pid, 'write', pid, write_message([noise])))
        gap_index = next(i for i, p in enumerate(base['phases']) if p['id'] == 'gap')
        base['phases'][gap_index:gap_index + 1] = gaps
        if axis == 'boundary':
            forbidden = next(f['value'] for f in base['facts'] if f['policy'] != 'retain')
            base['assertions'] = [r for r in base['assertions'] if r['type'] != 'memory_absent']
            base['assertions'].extend({'id': 'storage-' + p['id'], 'phase': p['id'],
                                       'type': 'memory_absent', 'forbidden': [forbidden]}
                                      for p in base['phases'])
        target_rule = (base['assertions'][0] if axis == 'discrimination' else
                       next(r for r in reversed(base['assertions'])
                            if r['type'] in ('response_value', 'artifact_json')))
        objective = copy.deepcopy(target_rule)
        objective['id'] = 'memory_dependent_objective'
        target_subject = (next(f['subject'] for f in base['facts'] if f['policy'] == 'retain')
                          if axis == 'boundary' else original['facts'][-1 if axis == 'retrieval' else 0]['subject'])
        pair_id = 'pair-' + token(world_seed, axis, index, 'pair')
        order = ('provided', 'withheld') if int(pair_id[-1], 16) % 2 else ('withheld', 'provided')
        for arm in order:
            case = copy.deepcopy(base)
            case['id'] = 'episode-' + token(world_seed, axis, index, arm)
            case['stratum'] = f'{original["stratum"]}/{arm}/gap-{interference_sessions}'
            case['intervention'] = {'pair_id': pair_id, 'arm': arm, 'split': split,
                                    'interference_sessions': interference_sessions, 'objective': copy.deepcopy(objective)}
            replacements = {}
            if arm == 'withheld':
                for f in case['facts']:
                    if f['subject'] == target_subject:
                        marker = token(world_seed, axis, index, f'withheld-{f["key"]}-{f["revision"]}')
                        replacements[(f['subject'], f['key'], f['revision'])] = fact(
                            '无关办公事项-' + pair_id[-8:], f['key'], 'CONTROL_' + marker,
                            policy=f['policy'], revision=f['revision'])
                case['facts'] = [copy.deepcopy(replacements.get((f['subject'], f['key'], f['revision']), f))
                                 for f in case['facts']]
                for rule in case['assertions']:
                    if rule['type'] == 'artifact_json':
                        rule['type'] = 'artifact_absent'
                        rule.pop('expected')
                    elif rule['type'] == 'response_value' and (
                            axis != 'discrimination' or rule['id'] == 'original'):
                        rule.update(type='response_absent', forbidden=[str(rule.pop('expected'))], require_abstention=True)
                        rule.pop('alternatives', None)
            for p in case['phases']:
                if p['id'] in inputs:
                    records = [copy.deepcopy(replacements.get((f['subject'], f['key'], f['revision']), f))
                               for f in inputs[p['id']]]
                    p['message'] = write_message(records)
            cases.append(case)
    data.update(seed=seed, dataset_id=f'kmb-episodes-{split}-{seed}-{per_dimension}-gap{interference_sessions}',
                protocol='kmb.episodes/v1', cases=cases,
                provenance={'kind': 'programmatic_synthetic', 'human_gold': False,
                            'oracle': 'versioned facts and actual artifacts; matched relevant-source withholding',
                            'split_unit': 'disjoint generated fact worlds, not held-out templates',
                            'intervention': 'relevant source provided versus replaced by unrelated same-count records'})
    return data


def generate_episodes(seed: int = 42, split: str = 'test', per_dimension: int = 4,
                      interference_sessions: int = 4) -> dict:
    data = _build_episodes(seed, split, per_dimension, interference_sessions)
    validate_dataset(data)
    return data
