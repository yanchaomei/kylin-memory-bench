#!/usr/bin/env python3
"""Verified trial analysis: reliable success and paired episode comparisons."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import html
from itertools import combinations
import json
from math import comb
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from kylin_memory_bench.evidence import build_manifest, verify_run, write_json
from kylin_memory_bench.model import parse_json
from kylin_memory_bench.reporting import compare_scores, render_report
from kylin_memory_bench.scoring import score_run


def reliability(trials):
    if not trials or not trials[0]:
        raise ValueError('reliability requires non-empty trials')
    ids = set(trials[0])
    if any(set(t) != ids for t in trials):
        raise ValueError('reliability requires the same case inventory in every trial')
    if any(v is not None and type(v) is not bool for t in trials for v in t.values()):
        raise ValueError('case outcomes must be boolean or unobservable')
    n = len(trials)
    successes = {cid: sum(t[cid] is True for t in trials) for cid in sorted(ids)}
    powers = {str(k): statistics.mean(comb(c, k) / comb(n, k) for c in successes.values())
              for k in range(1, n + 1)}
    return {'cases': len(ids), 'repeats': n, 'pass_power': powers,
            'all_repeats_success_rate': powers[str(n)],
            'repeat_state_agreement': sum(len({t[cid] for t in trials}) == 1 for cid in ids) / len(ids),
            'scorable_fraction': sum(v is not None for t in trials for v in t.values()) / (len(ids) * n),
            'successes_per_case': successes,
            'interpretation': 'operational success; inconclusive gets no success credit, not an ability-failure claim'}


def exact_mcnemar(first, second):
    if set(first) != set(second) or any(type(v) is not bool for t in (first, second) for v in t.values()):
        raise ValueError('system comparison requires matched binary episode outcomes')
    b = sum(first[k] and not second[k] for k in first)
    c = sum(second[k] and not first[k] for k in first)
    discordant = b + c
    p = min(1.0, 2 * sum(comb(discordant, i) for i in range(min(b, c) + 1)) / (2 ** discordant)) if discordant else 1.0
    return {'episodes': len(first), 'only_first': b, 'only_second': c,
            'both_success': sum(first[k] and second[k] for k in first),
            'neither_success': sum(not first[k] and not second[k] for k in first),
            'exact_two_sided_p': p if first else None}


def summarize(scores):
    comparison = compare_scores(scores)
    groups = defaultdict(list)
    for score in scores:
        groups[score['agent']].append(score)
    agents = []
    episode_outcomes = {}
    episode_complete = {}
    for name, trials in sorted(groups.items()):
        values = [{c['case_id']: c['passed'] for c in t['cases']} for t in trials]
        metrics = reliability(values)
        pair_rows = defaultdict(list)
        for trial in trials:
            for case in trial['cases']:
                if 'intervention' in case:
                    pair_rows[case['intervention']['pair_id']].append(case['passed'])
        if pair_rows:
            if any(len(v) != 2 * len(trials) for v in pair_rows.values()):
                raise ValueError('episode reliability needs both arms in every repeat')
            outcomes = {k: all(v is True for v in rows) for k, rows in pair_rows.items()}
            complete = {k: all(v is not None for v in rows) for k, rows in pair_rows.items()}
            episode_outcomes[name] = outcomes
            episode_complete[name] = complete
            metrics['whole_episode_all_repeats_success_rate'] = statistics.mean(outcomes.values())
            metrics['whole_episode_complete_fraction'] = statistics.mean(complete.values())
            metrics['independent_episodes'] = len(outcomes)
        agents.append({'name': name, **metrics})
    contrasts = []
    for first, second in combinations(sorted(episode_outcomes), 2):
        if len(groups[first]) != len(groups[second]):
            contrasts.append({'first': first, 'second': second, 'comparable': False,
                              'reason': 'all-repeat endpoints require the same number of repeats'})
            continue
        a, b = episode_outcomes[first], episode_outcomes[second]
        if set(a) != set(b):
            raise ValueError('systems have different episode inventories')
        complete_ids = [k for k in a if episode_complete[first][k] and episode_complete[second][k]]
        contrasts.append({'first': first, 'second': second, 'comparable': True,
                          'endpoint': 'both arms policy-correct in every repeat',
                          'operational': exact_mcnemar(a, b),
                          'complete_only': exact_mcnemar({k: a[k] for k in complete_ids}, {k: b[k] for k in complete_ids}),
                          'complete_subset_coverage': len(complete_ids) / len(a) if a else 0})
    return {'schema': 'kmb.reliability/v1', 'dataset_sha256': comparison['dataset_sha256'],
            'agents': agents, 'system_contrasts': contrasts,
            'sampling_unit': 'independent episode; correlated arms and repeat outcomes are not new episodes',
            'source_availability_gain': 'reported separately in comparison.json; not backend-disabling ablation'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('runs', type=Path, nargs='+')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    scores = []
    for path in args.runs:
        check = verify_run(path)
        if not check['ok']:
            raise ValueError('trial evidence verification failed: ' + str(path))
        data = parse_json((path / 'dataset.json').read_text())
        run = parse_json((path / 'run.json').read_text())
        scores.append(score_run(data, run))
    result = summarize(scores)
    render_report(scores, args.out)
    write_json(args.out / 'reliability.json', result)
    with (args.out / 'reliability.csv').open('w', encoding='utf8', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['agent', 'cases', 'repeats', 'scorable_fraction', 'all_repeats_success_rate', 'pass_power'])
        for a in result['agents']:
            writer.writerow([a['name'], a['cases'], a['repeats'], a['scorable_fraction'],
                             a['all_repeats_success_rate'], json.dumps(a['pass_power'])])
    rows = []
    for a in result['agents']:
        powers = ', '.join(f'pass^{k}: {100*v:.1f}%' for k, v in a['pass_power'].items())
        rows.append(f'<tr><td>{html.escape(a["name"])}</td><td>{a["cases"]}</td><td>{a["repeats"]}</td>'
                    f'<td>{100*a["scorable_fraction"]:.1f}%</td><td>{html.escape(powers)}</td>'
                    f'<td>{100*a["all_repeats_success_rate"]:.1f}%</td></tr>')
    document = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>Kylin Memory Bench | 重复可靠性</title><style>body{font:14px/1.7 system-ui,sans-serif;margin:0;color:#25333a;letter-spacing:0}'
                'main{max-width:1180px;margin:auto;padding:32px 20px}h1{font-size:24px}table{border-collapse:collapse;width:100%}'
                'td,th{padding:12px;border-bottom:1px solid #dce4e7;text-align:left;white-space:nowrap}th{background:#edf3f2}'
                '.scroll{overflow:auto}a{color:#07816d}p{max-width:900px}</style><main><h1>重复可靠性与配对比较</h1>'
                '<p><a href="report.html">六维结果、资料收益与逐例证据</a></p><div class="scroll"><table><thead><tr>'
                '<th>智能体</th><th>每轮案例</th><th>轮次</th><th>可评分比例</th><th>连续成功估计</th><th>全部轮次都成功</th>'
                '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
                '<p>pass^k 是从已分配的重复中抽取 k 次、要求都成功的估计，不是至少一次成功的 pass@k。'
                '运行或证据异常不给成功分，并同时公布覆盖率；该指标描述端到端运行可靠性，不把异常当作模型能力失败。</p>'
                '<p>系统差异按独立 episode 比较：两臂在全部轮次均正确才算可靠成功。精确 McNemar 检验及完整证据子集结果保存在 reliability.json。'
                '主资料收益仍在配对章节单列，不以可靠性取代；小样本不支持通用系统排名。</p></main></html>')
    (args.out / 'reliability.html').write_text(document, encoding='utf8')
    build_manifest(args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
