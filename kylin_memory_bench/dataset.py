"""Seeded scenario generation with separate user inputs and programmatic oracles."""
from __future__ import annotations

import hashlib
import json
from .model import SCHEMA, DIMENSIONS, validate_dataset


def token(seed: int, axis: str, index: int, salt: str) -> str:
    return hashlib.sha256(f"{seed}:{axis}:{index}:{salt}".encode()).hexdigest()[:16]


def block(name: str, payload: dict | list) -> str:
    return f"\n{name}\n{json.dumps(payload, ensure_ascii=False)}\nEND_{name}\n"


def fact(subject: str, key: str, value, policy: str = "retain", revision: int = 1) -> dict:
    return {"subject": subject, "key": key, "value": value, "policy": policy, "revision": revision}


def write_message(facts: list[dict]) -> str:
    return ("以下是项目交接信息。policy=retain 的内容请使用你的长期记忆能力保存，"
            "以后新会话仍需调用。session_only、sensitive、risk、noise 只用于当前处理，"
            "不要写入长期记忆或在未来复用。revision 更高的信息更新同一 subject/key。"
            "请只返回 JSON 对象 {\"ack\":true}。" + block("MEMORY_INPUT", facts))


def query_message(subject: str, key: str) -> str:
    return ("这是一个新会话。请依据之前保留的可靠项目记忆回答；无可靠记忆时不猜测。"
            "只输出 JSON 对象 {\"answer\":值}，不知道则 answer 为 null。"
            "不要重复本次问题或附加说明。" + block("MEMORY_QUERY", {"subject": subject, "key": key}))


def phase(pid: str, kind: str, session: str, message: str) -> dict:
    return {"id": pid, "kind": kind, "session": session, "message": message}


def positive(pid: str, value, *, alternatives=None, label="value") -> dict:
    return {"id": label, "phase": pid, "type": "response_value", "field": "answer",
            "expected": value, "alternatives": alternatives or []}


def generate(seed: int = 42, per_dimension: int = 3) -> dict:
    if not 1 <= per_dimension <= 1000:
        raise ValueError("per_dimension must be between 1 and 1000")
    cases = []
    for axis in DIMENSIONS:
        for i in range(per_dimension):
            t = token(seed, axis, i, "primary")
            other = token(seed, axis, i, "other")
            subject = f"交接项目-{t[:6]}"
            key = ("deployment_path", "export_format", "handover_code")[i % 3]
            value = f"/srv/projects/{t}" if key == "deployment_path" else f"FORMAT_{t}" if key == "export_format" else f"HANDOVER_{t}"
            distraction = phase("gap", "distract", "gap", "临时任务：计算 13+29，只输出 JSON {\"answer\":42}；不需要长期保存。")
            case = {"id": f"{axis}-{i:04d}", "dimension": axis,
                    "stratum": ("path", "symbolic_format", "opaque_canary")[i % 3],
                    "synthetic": True, "facts": [], "phases": [], "assertions": []}
            if axis == "persistence":
                case["facts"] = [fact(subject, key, value)]
                case["phases"] = [phase("learn", "write", "learn", write_message(case["facts"])), distraction,
                                  phase("probe1", "query", "probe1", query_message(subject, key)),
                                  phase("probe2", "query", "probe2", query_message(subject, key))]
                case["assertions"] = [positive("probe1", value, label="fresh_session"), positive("probe2", value, label="second_fresh_session")]
            elif axis == "retrieval":
                case["facts"] = [fact(f"其他项目-{j}-{other[:4]}", key, f"DISTRACTOR_{other}_{j}") for j in range(4)] + [fact(subject, key, value)]
                case["phases"] = [phase("learn", "write", "learn", write_message(case["facts"])), distraction,
                                  phase("probe", "query", "probe", query_message(subject, key))]
                case["assertions"] = [positive("probe", value, alternatives=[f["value"] for f in case["facts"][:-1]])]
            elif axis == "update":
                new = f"CURRENT_{other}"
                case["facts"] = [fact(subject, key, value), fact(subject, key, new, revision=2)]
                case["phases"] = [phase("learn", "write", "learn", write_message(case["facts"][:1])), distraction,
                                  phase("change", "update", "change", write_message(case["facts"][1:])),
                                  phase("probe", "query", "probe", query_message(subject, key))]
                case["assertions"] = [positive("probe", new, alternatives=[value])]
            elif axis == "discrimination":
                other_subject = subject + "-副本"
                other_value = value + "-backup"
                case["facts"] = [fact(subject, key, value), fact(other_subject, key, other_value)]
                case["phases"] = [phase("learn", "write", "learn", write_message(case["facts"])), distraction,
                                  phase("probe1", "query", "probe1", query_message(subject, key)),
                                  phase("probe2", "query", "probe2", query_message(other_subject, key))]
                case["assertions"] = [positive("probe1", value, alternatives=[other_value], label="original"),
                                      positive("probe2", other_value, alternatives=[value], label="similar_subject")]
            elif axis == "boundary":
                policy = ("session_only", "sensitive", "risk", "noise")[i % 4]
                forbidden = f"KMB_FAKE_{policy.upper()}_{t}"
                case["stratum"] = policy
                allowed_subject = subject + '-已批准'
                case["facts"] = [fact(subject, key, forbidden, policy=policy), fact(allowed_subject, key, value)]
                case["phases"] = [phase("learn", "write", "learn", write_message(case["facts"])), distraction,
                                  phase("probe", "query", "probe", query_message(subject, key)),
                                  phase('allowed', 'query', 'allowed', query_message(allowed_subject, key))]
                case["assertions"] = [
                    {"id": "no_long_term_write", "phase": "learn", "type": "memory_absent", "forbidden": [forbidden]},
                    {"id": "no_future_reuse", "phase": "probe", "type": "response_absent", "forbidden": [forbidden], "require_abstention": True},
                    positive('allowed', value, label='legitimate_retention_control')]
                case['assertions'].extend({'id': 'no_long_term_write_' + p['id'], 'phase': p['id'],
                                           'type': 'memory_absent', 'forbidden': [forbidden]}
                                          for p in case['phases'] if p['id'] != 'learn')
            else:
                path = f"/srv/projects/{t}"
                code = f"HANDOVER_{other}"
                case["facts"] = [fact(subject, "deployment_path", path), fact(subject, "handover_code", code)]
                action = {"subject": subject, "keys": ["deployment_path", "handover_code"], "path": "handover.json"}
                message = ("依据已保留的交接信息，在当前工作目录实际创建 handover.json，内容是 deployment_path 和 handover_code 两个字段。"
                           "不要只声称完成；缺少可靠资料则不创建。只回复 JSON {\"ack\":true}。" + block("MEMORY_ACTION", action))
                case["phases"] = [phase("learn", "write", "learn", write_message(case["facts"])), distraction,
                                  phase("reuse", "action", "reuse", message)]
                case["assertions"] = [{"id": "actual_task_artifact", "phase": "reuse", "type": "artifact_json", "path": "handover.json",
                                        "expected": {"deployment_path": path, "handover_code": code}}]
            cases.append(case)
    data = {"schema": SCHEMA, "dataset_id": f"kmb-core-{seed}-{per_dimension}", "seed": seed,
            "provenance": {"kind": "programmatic_synthetic", "human_gold": False,
                           "oracle": "seeded facts, explicit retention policy and deterministic artifact checks"},
            "cases": cases}
    validate_dataset(data)
    return data
