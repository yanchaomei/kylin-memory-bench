"""Six-axis comparison, repeat agreement, CSV and self-contained HTML/SVG."""
from __future__ import annotations

import csv
import html
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

from .evidence import build_manifest, write_json
from .model import DIMENSIONS, DIMENSION_LABELS
from .paired import summarize_pairs

COLORS = ('#07816d', '#c7503d', '#326da8', '#9565ad', '#8a741d', '#424b57')


def compare_scores(scores: list[dict]) -> dict:
    if not scores:
        raise ValueError('comparison requires at least one score')
    if len({s['dataset_sha256'] for s in scores}) != 1:
        raise ValueError('comparison requires the same frozen dataset')
    if len({s['agent_kind'] for s in scores}) != 1:
        raise ValueError('calibration fixtures and real agents must be reported separately')
    run_ids = [s['run_id'] for s in scores]
    if len(set(run_ids)) != len(run_ids):
        raise ValueError('the same run cannot be counted twice')
    groups = defaultdict(list)
    for score in scores:
        groups[score['agent']].append(score)
    agents = []
    for name, repeats in groups.items():
        conditions = {json.dumps({'configuration': s.get('configuration', {}), 'version': s.get('agent_version'),
                                  'source_sha256': s.get('source_sha256')}, sort_keys=True) for s in repeats}
        if len(conditions) != 1:
            raise ValueError('repeat conditions differ for agent ' + name + '; use distinct configuration names')
        dimensions = {}
        for dimension in DIMENSIONS:
            rows = [s['dimensions'][dimension] for s in repeats]
            values = [r['success_rate'] for r in rows if r['success_rate'] is not None]
            conditional = [r['score'] for r in rows if r['score'] is not None]
            dimensions[dimension] = {'success_rate': statistics.mean(values) if values else None,
                                     'score': statistics.mean(conditional) if conditional else None,
                                     'coverage': statistics.mean(r['coverage'] for r in rows),
                                     'stddev': statistics.pstdev(values) if values else None,
                                     'passed_per_run': [r['passed'] for r in rows],
                                     'total_per_run': [r['total'] for r in rows]}
        case_states = defaultdict(list)
        for score in repeats:
            for case in score['cases']:
                case_states[case['case_id']].append(case['status'])
        agreement = (sum(len(set(v)) == 1 for v in case_states.values()) / len(case_states)) if len(repeats) > 1 else None
        agents.append({'name': name, 'kind': repeats[0]['agent_kind'], 'repeats': len(repeats),
                       'run_ids': [s['run_id'] for s in repeats], 'dimensions': dimensions,
                       'repeat_agreement': agreement,
                       'environments': [s['environment'] for s in repeats],
                       'runtime': [s.get('runtime', {}) for s in repeats],
                       'configurations': [s.get('configuration', {}) for s in repeats],
                       'versions': [s.get('agent_version') for s in repeats]})
        if any('intervention' in c for s in repeats for c in s['cases']):
            agents[-1]['paired_summary'] = summarize_pairs(repeats)
    return {'schema': 'kmb.comparison/v1', 'dataset_sha256': scores[0]['dataset_sha256'],
            'agent_kind': scores[0]['agent_kind'], 'agents': agents,
            'real_agent_count': len(agents) if scores[0]['agent_kind'] == 'real' else 0,
            'metric': 'successful cases / all assigned cases; incomplete evidence receives no success credit',
            'repeat_unit': 'independent run; repeated cases are not pooled as new independent samples'}


def radar_svg(comparison: dict) -> str:
    svg = ET.Element('svg', {'xmlns': 'http://www.w3.org/2000/svg', 'viewBox': '0 0 660 550',
                             'role': 'img', 'aria-label': 'Six-dimensional memory benchmark comparison'})
    ET.SubElement(svg, 'rect', {'width': '660', 'height': '550', 'fill': '#ffffff'})
    center = (330, 242); radius = 175
    def point(axis, level):
        angle = -math.pi / 2 + axis * math.pi / 3
        return center[0] + radius * level * math.cos(angle), center[1] + radius * level * math.sin(angle)
    def points(values):
        return ' '.join(f'{x:.2f},{y:.2f}' for x, y in (point(i, v) for i, v in enumerate(values)))
    for level in (.2, .4, .6, .8, 1):
        ET.SubElement(svg, 'polygon', {'points': points([level] * 6), 'fill': 'none', 'stroke': '#dfe5e7', 'stroke-width': '1'})
        ET.SubElement(svg, 'text', {'x': '338', 'y': str(center[1] - radius * level + 15), 'fill': '#6c747b', 'font-size': '12'}).text = str(round(level * 100))
    for i, dimension in enumerate(DIMENSIONS):
        x, y = point(i, 1)
        ET.SubElement(svg, 'line', {'x1': str(center[0]), 'y1': str(center[1]), 'x2': str(x), 'y2': str(y), 'stroke': '#e2e7e9'})
        x, y = point(i, 1.21)
        ET.SubElement(svg, 'text', {'x': str(x), 'y': str(y + 6), 'text-anchor': 'middle', 'fill': '#25333a',
                                   'font-size': '16', 'font-family': 'system-ui, sans-serif'}).text = DIMENSION_LABELS[dimension]
    for j, agent in enumerate(comparison['agents']):
        color = COLORS[j % len(COLORS)]
        values = [agent['dimensions'][d]['success_rate'] for d in DIMENSIONS]
        if all(v is not None for v in values):
            ET.SubElement(svg, 'polygon', {'points': points(values), 'fill': color, 'fill-opacity': '.07', 'stroke': color, 'stroke-width': '2.5'})
            for i, value in enumerate(values):
                x, y = point(i, value)
                ET.SubElement(svg, 'circle', {'cx': str(x), 'cy': str(y), 'r': '3.5', 'fill': color})
        x = 55 + (j % 3) * 205; y = 480 + (j // 3) * 27
        ET.SubElement(svg, 'line', {'x1': str(x), 'y1': str(y), 'x2': str(x + 22), 'y2': str(y), 'stroke': color, 'stroke-width': '3'})
        ET.SubElement(svg, 'text', {'x': str(x + 29), 'y': str(y + 5), 'font-size': '13', 'fill': '#25333a'}).text = agent['name']
    return ET.tostring(svg, encoding='unicode')


def percent(value):
    return f'{100*value:.1f}%' if value is not None else 'N/A'


def gain_label(value):
    return f'{100*value:+.1f} pp' if value is not None else 'N/A'


def render_report(scores: list[dict], output: Path) -> dict:
    comparison = compare_scores(scores)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / 'comparison.json', comparison)
    svg = radar_svg(comparison)
    (output / 'radar.svg').write_text(svg, encoding='utf8')
    with (output / 'metrics.csv').open('w', encoding='utf8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['agent', 'dimension', 'success_rate', 'scorable_accuracy', 'coverage', 'repeats', 'stddev', 'repeat_agreement'])
        for a in comparison['agents']:
            for d in DIMENSIONS:
                m = a['dimensions'][d]
                writer.writerow([a['name'], d, m['success_rate'], m['score'], m['coverage'], a['repeats'], m['stddev'], a['repeat_agreement']])
    escape = html.escape
    paired_agents = [a for a in comparison['agents'] if 'paired_summary' in a]
    paired_html = ''
    if paired_agents:
        paired_rows = []
        with (output / 'paired_metrics.csv').open('w', encoding='utf8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['agent', 'independent_pairs', 'complete_pairs', 'coverage', 'provided_target_rate',
                             'withheld_target_rate', 'mean_source_gain', 'bootstrap_95', 'withheld_safe_case_rate'])
            for a in paired_agents:
                m = a['paired_summary']
                writer.writerow([a['name'], m['independent_pairs'], m['complete_pairs'], m['complete_pair_coverage'],
                                 m['provided_target_rate'], m['withheld_target_rate'], m['mean_source_gain'],
                                 json.dumps(m['bootstrap_95']), m['withheld_safe_case_rate']])
                interval = ('[' + ', '.join(gain_label(v) for v in m['bootstrap_95']) + ']') if m['bootstrap_95'] else 'N/A'
                paired_rows.append(f'<tr><td>{escape(a["name"])}</td><td class="num">{m["complete_pairs"]}/{m["independent_pairs"]}</td>'
                                   f'<td class="num">{percent(m["provided_target_rate"])}</td><td class="num">{percent(m["withheld_target_rate"])}</td>'
                                   f'<td class="num">{gain_label(m["mean_source_gain"])}</td><td class="num">{interval}</td>'
                                   f'<td class="num">{percent(m["withheld_safe_case_rate"])}</td></tr>')
        paired_html = ('<section><h2>配对资料收益</h2><div class="table-wrap"><table><thead><tr><th>智能体</th>'
                       '<th class="num">完整配对</th><th class="num">提供资料时目标达成</th><th class="num">未提供资料时目标达成</th>'
                       '<th class="num">目标达成差值</th><th class="num">任务配对 Bootstrap 95%</th><th class="num">无资料安全行为</th>'
                       '</tr></thead><tbody>' + ''.join(paired_rows) + '</tbody></table></div>'
                       '<p class="meta">两侧查询相同，只改变相关资料是否提供。未知时正确拒答单独计入安全行为，不计为任务目标达成。'
                       '重复先在同一任务配对内平均；证据不完整的配对不用于差值估计，并保留覆盖率。这是资料可用性对照，不是关闭框架记忆后端。</p></section>')
    rows = []
    for a in comparison['agents']:
        for d in DIMENSIONS:
            m = a['dimensions'][d]
            rows.append(f'<tr><td>{escape(a["name"])}</td><td>{DIMENSION_LABELS[d]}</td>'
                        f'<td class="num">{percent(m["success_rate"])}</td><td class="num">{percent(m["coverage"])}</td>'
                        f'<td class="num">{percent(m["score"])}</td><td class="num">{a["repeats"]}</td></tr>')
    details = []
    for score in scores:
        for case in score['cases']:
            reasons = ''
            for r in case['assertions']:
                values = ('<p>期望：<code>' + escape(json.dumps(r.get('expected'), ensure_ascii=False))
                          + '</code><br>实际：<code>' + escape(json.dumps(r.get('actual'), ensure_ascii=False)) + '</code></p>') if 'actual' in r else ''
                reasons += (f'<li><strong>{escape(r["id"])}</strong> · {escape(r["outcome"])}<p>{escape(r["reason"])}</p>{values}'
                            f'<code>{escape(", ".join(r["evidence_refs"]))}</code></li>')
            if 'target_attainment' in case:
                r = case['target_attainment']
                reasons += f'<li><strong>任务目标达成</strong><p>{escape(r["reason"])}</p><code>{escape(", ".join(r["evidence_refs"]))}</code></li>'
            details.append(f'<details data-status="{escape(case["status"])}"><summary><span>{escape(score["agent"])} / {escape(score["run_id"][-8:])} / '
                           f'{escape(case["case_id"])}</span><span class="status {case["status"]}">{case["status"]}</span>'
                           f'</summary><ul>{reasons}</ul></details>')
    platforms = sorted({s['environment'].get('os_release', {}).get('PRETTY_NAME', s['environment'].get('system', 'unknown')) for s in scores})
    label = '真实智能体评测' if comparison['agent_kind'] == 'real' else '评分器校准 · 测试替身'
    template = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kylin Memory Bench | 评测报告</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f7;color:#25333a;font:14px/1.55 system-ui,-apple-system,sans-serif;letter-spacing:0}
header{background:#fff;border-bottom:1px solid #dce3e6;padding:24px max(24px,calc((100vw - 1180px)/2))}h1{font-size:25px;margin:0 0 6px;font-weight:650}h2{font-size:18px;margin:0 0 18px}p{margin:7px 0}.eyebrow{font-size:12px;color:#07816d;font-weight:650;margin-bottom:8px}
main{max-width:1228px;padding:28px 24px;margin:auto}.summary{display:grid;grid-template-columns:1fr 1fr;gap:30px;align-items:center;background:#fff;border-top:3px solid #07816d;padding:24px;margin-bottom:28px}.summary svg{width:100%;height:auto}.meta{color:#5c6870;font-size:13px;overflow-wrap:anywhere}.numbers{display:flex;gap:38px;padding:18px 0;border-top:1px solid #e1e7e9;margin-top:20px}.numbers strong{font-size:30px;font-weight:600;display:block}.numbers span{color:#63717a;font-size:12px}
section{margin:30px 0}table{border-collapse:collapse;width:100%;background:#fff}th{font-size:12px;color:#52616a;text-align:left;background:#edf1f2}td,th{padding:11px 14px;border-bottom:1px solid #e0e6e8}.num{text-align:right;font-variant-numeric:tabular-nums}.table-wrap{overflow:auto}details{background:#fff;border-bottom:1px solid #dfe6e8;padding:12px 16px}summary{cursor:pointer;display:flex;justify-content:space-between;gap:14px}details ul{padding-left:20px}details li{margin:16px 0}code{font:11px/1.6 ui-monospace,monospace;color:#68767e;overflow-wrap:anywhere}.status{font-size:12px;color:#65737b}.pass{color:#07816d}.fail{color:#b44336}.inconclusive{color:#856e18}select{padding:6px 10px;border:1px solid #ccd6db;border-radius:4px;background:#fff;color:inherit}footer{border-top:1px solid #d7e0e4;color:#65757e;padding-top:20px;font-size:12px}@media(max-width:800px){.summary{grid-template-columns:1fr;padding:16px}header{padding:20px}main{padding:20px 14px}h1{font-size:22px}.numbers{gap:24px}td,th{white-space:nowrap}}
</style><header><div class="eyebrow">Kylin Memory Bench / {{LABEL}}</div><h1>智能体长期记忆 · 六维评测报告</h1><p class="meta">{{PLATFORMS}}</p></header><main>
<div class="summary"><div>{{SVG}}</div><div><h2>从记忆写入到实际任务</h2><p>长期保持、记忆调用、动态更新、相近区分、边界识别、任务复用。</p><div class="numbers"><div><strong>{{AGENTS}}</strong><span>智能体配置</span></div><div><strong>{{RUNS}}</strong><span>独立运行</span></div><div><strong>{{CASES}}</strong><span>每轮案例</span></div></div><p class="meta">雷达值：成功案例 / 全部分配案例。覆盖率：证据完整、可评分案例 / 全部案例。每条判定保留原因与证据引用。</p><p class="meta">数据指纹<br><code>{{HASH}}</code></p></div></div>
<section><h2>多维结果</h2><div class="table-wrap"><table><thead><tr><th>智能体</th><th>维度</th><th class="num">成功率</th><th class="num">覆盖率</th><th class="num">可评分正确率</th><th class="num">运行数</th></tr></thead><tbody>{{ROWS}}</tbody></table></div></section>
{{PAIRED}}<section><h2>逐例判定 <select aria-label="结果筛选" id="filter"><option value="all">全部</option><option value="pass">通过</option><option value="fail">失败</option><option value="inconclusive">证据不完整</option></select></h2>{{DETAILS}}</section><footer>评分方法：结构化值核对、已声明长期记忆文件检查、实际任务文件核对。程序化合成数据；各重复轮次分别保留，不合并冒充新增独立案例。</footer></main>
<script>document.getElementById('filter').addEventListener('change',e=>document.querySelectorAll('details').forEach(d=>d.hidden=e.target.value!=='all'&&d.dataset.status!==e.target.value))</script></html>'''
    values = {'LABEL': label, 'PLATFORMS': escape(' · '.join(platforms)), 'SVG': svg,
              'AGENTS': str(len(comparison['agents'])), 'RUNS': str(len(scores)), 'CASES': str(len(scores[0]['cases'])),
              'HASH': comparison['dataset_sha256'], 'ROWS': ''.join(rows), 'DETAILS': ''.join(details), 'PAIRED': paired_html}
    for key, value in values.items():
        template = template.replace('{{' + key + '}}', value)
    (output / 'report.html').write_text(template, encoding='utf8')
    build_manifest(output)
    return comparison
