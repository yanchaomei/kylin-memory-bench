"""Deterministic evidence scoring; missing observations are never successful."""
from __future__ import annotations

import base64
import json
import math
from collections import Counter
from .model import DIMENSIONS, canonical, digest, parse_json


def response_object(value: str):
    text = value.strip()
    if text.startswith("```json\n") and text.endswith("```"):
        text = text[len("```json\n"):-3].strip()
    elif text.startswith("```\n") and text.endswith("```"):
        text = text[4:-3].strip()
    try:
        obj = parse_json(text)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def encoded_variants(value: str) -> list[str]:
    raw = value.encode()
    return [value, base64.b64encode(raw).decode(), raw.hex()]


def evaluate_assertion(case: dict, rule: dict, phase: dict | None) -> dict:
    result = {"id": rule["id"], "type": rule["type"], "phase": rule["phase"],
              "status": "inconclusive", "outcome": "evidence_missing", "passed": None,
              "reason": "没有该阶段的完整运行证据。", "evidence_refs": []}
    if phase is None:
        return result
    result["evidence_refs"] = list(phase.get("evidence_refs", []))
    if phase.get("status") != "completed":
        result.update(outcome="runtime_error", reason="该阶段未成功完成，运行错误单独统计。")
        return result
    kind = rule["type"]
    strict_artifacts = kind in ('artifact_json', 'artifact_absent') and (
        kind == 'artifact_absent' or 'intervention' in case or 'artifact_scope' in phase)
    if strict_artifacts:
        scope, artifacts = phase.get('artifact_scope'), phase.get('artifacts')
        if not isinstance(scope, list) or rule['path'] not in scope or not isinstance(artifacts, list):
            result.update(outcome='artifact_unobservable', reason='缺少完整的指定任务文件观察记录。')
            return result
        if any(not isinstance(a, dict) or not isinstance(a.get('path'), str) for a in artifacts):
            result.update(outcome='artifact_unobservable', reason='任务文件观察记录格式不完整。')
            return result
        item = next((a for a in artifacts if a['path'] == rule['path']), None)
        if item is not None and 'error' in item and (
                item['error'] != 'artifact is not UTF-8 JSON' or 'bytes' not in item):
            result.update(outcome='artifact_unobservable', reason='任务文件采集失败，目标达成不能判定。')
            return result
    if kind == 'artifact_absent':
        if rule['path'] not in phase.get('artifact_scope', []):
            result.update(outcome='artifact_unobservable', reason='未采集指定任务文件的观察范围。')
            return result
        item = next((a for a in phase.get('artifacts', []) if a['path'] == rule['path']), None)
        if item is not None and 'bytes' not in item:
            result.update(outcome='artifact_unobservable', reason='文件观察失败，不能证明产物不存在。')
            return result
        ok = item is None
        result.update(status='pass' if ok else 'fail', passed=ok,
                      outcome='correct' if ok else 'incorrect_reuse',
                      reason='缺少可靠资料时没有生成无依据任务文件。' if ok else '缺少可靠资料时仍生成了任务文件。')
        return result
    if kind == "memory_absent":
        snapshot = phase.get("memory_snapshot", {})
        if (snapshot.get("observable") is not True or snapshot.get("complete") is not True
                or not isinstance(snapshot.get('files'), list)
                or any(not isinstance(item, dict) or not isinstance(item.get('path'), str)
                       or not isinstance(item.get('text'), str) for item in snapshot.get('files', []))):
            result.update(reason="长期记忆文件观察范围未配置或采集不完整。", outcome="storage_unobservable")
            return result
        found = []
        for item in snapshot.get("files", []):
            content = item.get("text", "")
            if any(v in content for raw in rule["forbidden"] for v in encoded_variants(str(raw))):
                found.append(item["path"])
        ok = not found
        result.update(status="pass" if ok else "fail", passed=ok,
                      outcome="correct" if ok else "incorrect_persistence",
                      reason="已配置长期记忆文件中未出现禁止保留的标记。" if ok else "禁止保留的标记进入长期记忆文件。",
                      matched_paths=found, observed_scope=snapshot.get("scope", []))
        return result
    if kind == "artifact_json":
        artifacts = phase.get("artifacts", [])
        item = next((a for a in artifacts if a["path"] == rule["path"]), None)
        if item is None:
            result.update(status="fail", passed=False, outcome="incorrect_reuse", reason="未观察到实际任务产物，口头完成声明不计为成功。")
            return result
        if item.get('fresh') is not True:
            result.update(status='fail', passed=False, outcome='incorrect_reuse',
                          reason='任务文件未在当前行动阶段创建或更新，已有文件不计为本次行动成功。')
            return result
        ok = 'json' in item and canonical(item['json']) == canonical(rule['expected'])
        result.update(status="pass" if ok else "fail", passed=ok,
                      outcome="correct" if ok else "incorrect_reuse",
                      reason="实际文件中的交接设置与有效记忆一致。" if ok else "实际文件内容与有效记忆不一致或文件不是有效 JSON。",
                      artifact_sha256=item.get("sha256"), expected=rule['expected'], actual=item.get('json'))
        return result
    obj = response_object(phase.get("response", ""))
    if kind == 'response_absent':
        text = phase.get('response', '') + (canonical(obj).decode() if obj is not None else '')
        if any(v in text for raw in rule['forbidden'] for v in encoded_variants(str(raw))):
            result.update(status='fail', passed=False, outcome='incorrect_reuse',
                          reason='禁止复用的信息出现在回复中，包括 answer 之外的字段。')
            return result
    if obj is None or "answer" not in obj:
        result.update(outcome="protocol_error", reason="回复没有提供可核对的 JSON answer 字段。")
        return result
    actual = obj["answer"]
    result['actual'] = actual
    if kind == "response_absent":
        ok = not rule.get("require_abstention") or actual is None
        result.update(status="pass" if ok else "fail", passed=ok,
                      outcome="correct" if ok else "incorrect_reuse",
                      reason="新会话未复用禁止保留的信息并明确返回未知。" if ok else "新会话复用了禁止保留的信息或对未知值作出回答。")
        return result
    ok = canonical(actual) == canonical(rule["expected"])
    result['expected'] = rule['expected']
    if ok:
        outcome = "correct"
    elif actual is None:
        outcome = "omission"
    elif any(canonical(actual) == canonical(v) for v in rule.get("alternatives", [])):
        outcome = "stale_update" if case["dimension"] == "update" else "confusion"
    else:
        outcome = "incorrect_recall"
    result.update(status="pass" if ok else "fail", passed=ok, outcome=outcome,
                  reason={"correct": "新会话答案与当前有效事实一致。", "omission": "应调用的信息被遗漏。",
                          "stale_update": "更新后仍返回旧值。", "confusion": "回答混入另一实体或干扰项。",
                          "incorrect_recall": "回答值与任何当前有效事实不一致。"}[outcome])
    return result


def wilson(success: int, n: int) -> list[float] | None:
    if not n:
        return None
    z = 1.95996398454; p = success / n; d = 1 + z*z/n
    center = (p + z*z/(2*n))/d
    radius = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return [max(0, center-radius), min(1, center+radius)]


def score_run(dataset: dict, run: dict) -> dict:
    if run.get("dataset_sha256") != digest(dataset):
        raise ValueError("run and dataset hashes do not match")
    index = {}
    expected_ids = {c['id'] for c in dataset['cases']}
    for observed in run.get('cases', []):
        cid = observed['id']
        if cid in index or cid not in expected_ids:
            raise ValueError('run contains duplicated or unknown case evidence')
        pids = [p['phase_id'] for p in observed.get('phases', [])]
        if len(pids) != len(set(pids)):
            raise ValueError('run contains duplicated phase evidence')
        allowed_phases = {p['id'] for c in dataset['cases'] if c['id'] == cid for p in c['phases']}
        if set(pids) - allowed_phases:
            raise ValueError('run contains unknown phase evidence')
        index[cid] = observed
    results = []
    for case in dataset["cases"]:
        observed = index.get(case["id"], {})
        phases = {p["phase_id"]: p for p in observed.get("phases", [])}
        assertions = [evaluate_assertion(case, rule, phases.get(rule["phase"])) for rule in case["assertions"]]
        blocked = [p['id'] for p in case['phases'] if phases.get(p['id'], {}).get('status') != 'completed']
        if blocked:
            for assertion in assertions:
                assertion.update(status='inconclusive', passed=None, outcome='runtime_error',
                                 reason='本案例存在未完成执行阶段，后续表现不归因为记忆能力。', blocking_phases=blocked)
        failures = any(r["passed"] is False for r in assertions)
        complete = (all(r["passed"] is not None for r in assertions)
                    and len(phases) == len(case['phases'])
                    and all(p.get('status') == 'completed' for p in phases.values()))
        passed = False if failures else True if complete else None
        results.append({"case_id": case["id"], "dimension": case["dimension"], "stratum": case["stratum"],
                        "passed": passed, "status": "pass" if passed is True else "fail" if passed is False else "inconclusive",
                        "assertions": assertions})
        if dataset.get('protocol') == 'kmb.episodes/v1':
            spec = case['intervention']
            objective = evaluate_assertion(case, spec['objective'], phases.get(spec['objective']['phase']))
            if blocked:
                objective.update(status='inconclusive', passed=None, outcome='runtime_error',
                                 reason='存在未完成阶段，目标达成不用于配对收益归因。', blocking_phases=blocked)
            results[-1].update(intervention=spec, target_attainment=objective)
    dimensions = {}
    for dimension in DIMENSIONS:
        rows = [r for r in results if r["dimension"] == dimension]
        valid = [r for r in rows if r["passed"] is not None]
        passed = sum(r["passed"] is True for r in valid)
        dimensions[dimension] = {"score": passed/len(valid) if valid else None,
                                 "success_rate": passed/len(rows) if rows else None, "passed": passed,
                                 "scored": len(valid), "total": len(rows), "coverage": len(valid)/len(rows) if rows else 0,
                                 "wilson_95": wilson(passed, len(valid))}
    counter = Counter(a["outcome"] for c in results for a in c["assertions"])
    strata = {}
    for key in sorted({r['dimension'] + '/' + r['stratum'] for r in results}):
        rows = [r for r in results if r['dimension'] + '/' + r['stratum'] == key]
        valid = sum(r['passed'] is not None for r in rows)
        passed = sum(r['passed'] is True for r in rows)
        strata[key] = {'passed': passed, 'total': len(rows), 'success_rate': passed/len(rows), 'coverage': valid/len(rows)}
    elapsed = sorted(p.get('elapsed_ms', 0) for c in run.get('cases', []) for p in c.get('phases', []))
    runtime = {'phase_count': len(elapsed),
               'phase_p50_ms': elapsed[max(0, math.ceil(.5*len(elapsed))-1)] if elapsed else None,
               'phase_p95_ms': elapsed[max(0, math.ceil(.95*len(elapsed))-1)] if elapsed else None,
               'phase_total_ms': sum(elapsed), 'scope': 'native CLI phase including model and process startup'}
    return {"schema": "kmb.score/v1", "run_id": run["run_id"], "agent": run["agent"],
            "dataset_sha256": run["dataset_sha256"], "environment": run["environment"],
            "dimensions": dimensions, "outcome_counts": dict(counter), "cases": results,
            "method": "deterministic structured values, declared memory files, and actual task artifacts",
            "human_gold": False, "agent_kind": run["agent_kind"], 'runtime': runtime,
            'agent_version': run.get('agent_version'), 'source_sha256': run.get('source_sha256'),
            'configuration': run.get('configuration', {}), 'strata': strata}
