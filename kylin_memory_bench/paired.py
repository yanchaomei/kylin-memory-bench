"""Source-availability gains clustered by independent episode, not probe count."""
from __future__ import annotations

import random
import statistics

from .model import canonical


def bootstrap_interval(values: list[float], seed: int, resamples: int) -> list[float] | None:
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    samples = sorted(statistics.mean(values[rng.randrange(len(values))] for _ in values)
                     for _ in range(resamples))
    return [samples[int(.025 * (resamples - 1))], samples[int(.975 * (resamples - 1))]]


def summarize_pairs(scores: list[dict], *, seed: int = 20261009, resamples: int = 2000) -> dict:
    if not 100 <= resamples <= 10000:
        raise ValueError('bootstrap resamples must be between 100 and 10000')
    if len({s['run_id'] for s in scores}) != len(scores):
        raise ValueError('paired summaries cannot count a run twice')
    runs = []
    dimensions = {}
    for score in scores:
        groups = {}
        for case in score['cases']:
            spec = case.get('intervention')
            if not isinstance(spec, dict) or spec.get('arm') not in ('provided', 'withheld'):
                raise ValueError('paired summary requires episode intervention records')
            groups.setdefault(spec['pair_id'], {})
            if spec['arm'] in groups[spec['pair_id']]:
                raise ValueError('paired summary contains duplicate arms')
            groups[spec['pair_id']][spec['arm']] = case
            dimensions[spec['pair_id']] = case['dimension']
        runs.append(groups)
    pair_ids = sorted({k for r in runs for k in r})
    rows = []
    complete_executions = safe_cases = 0
    for pair_id in pair_ids:
        trials = []
        for groups in runs:
            arms = groups.get(pair_id, {})
            if set(arms) != {'provided', 'withheld'}:
                trials.append({'gain': None, 'provided': None, 'withheld': None})
                continue
            one, two = arms['provided'], arms['withheld']
            if one['dimension'] != two['dimension'] or canonical(one['intervention']['objective']) != canonical(two['intervention']['objective']):
                raise ValueError('paired objectives or dimensions differ')
            values = [c['target_attainment']['passed'] for c in (one, two)]
            if any(v is not None and type(v) is not bool for v in values):
                raise ValueError('target attainment must be boolean or unobservable')
            safe_cases += two['passed'] is True
            gain = None if None in values else int(values[0]) - int(values[1])
            complete_executions += gain is not None
            trials.append({'gain': gain, 'provided': values[0], 'withheld': values[1]})
        complete = all(t['gain'] is not None for t in trials)
        rows.append({'pair_id': pair_id, 'dimension': dimensions[pair_id], 'repeats': len(scores),
                     'complete': complete, 'mean_gain': statistics.mean(t['gain'] for t in trials) if complete else None,
                     'provided_target_rate': statistics.mean(t['provided'] for t in trials) if complete else None,
                     'withheld_target_rate': statistics.mean(t['withheld'] for t in trials) if complete else None,
                     'trials': trials})
    valid = [r for r in rows if r['complete']]
    gains = [r['mean_gain'] for r in valid]
    total = len(pair_ids) * len(scores)
    by_dimension = {}
    for dimension in sorted(set(dimensions.values())):
        subset = [r for r in rows if r['dimension'] == dimension]
        observed = [r['mean_gain'] for r in subset if r['complete']]
        by_dimension[dimension] = {'pairs': len(subset), 'complete_pairs': len(observed),
                                   'mean_source_gain': statistics.mean(observed) if observed else None}
    return {'schema': 'kmb.paired/v1', 'intervention': 'relevant source availability; not backend memory disabling',
            'independent_pairs': len(pair_ids), 'complete_pairs': len(valid), 'total_pair_executions': total,
            'complete_pair_coverage': len(valid) / len(pair_ids) if pair_ids else 0,
            'complete_pair_execution_coverage': complete_executions / total if total else 0,
            'mean_source_gain': statistics.mean(gains) if gains else None,
            'provided_target_rate': statistics.mean(r['provided_target_rate'] for r in valid) if valid else None,
            'withheld_target_rate': statistics.mean(r['withheld_target_rate'] for r in valid) if valid else None,
            'withheld_safe_case_rate': safe_cases / total if total else None,
            'bootstrap_95': bootstrap_interval(gains, seed, resamples), 'bootstrap_seed': seed, 'resamples': resamples,
            'sampling_unit': 'independent pair; repeats averaged within pair; incomplete clusters excluded with coverage',
            'by_dimension': by_dimension, 'pairs': rows}
