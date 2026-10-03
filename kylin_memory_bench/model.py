"""Stable dataset contracts. Oracles never enter adapter requests."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any

SCHEMA = "kmb.dataset/v1"
DIMENSIONS = ("persistence", "retrieval", "update", "discrimination", "boundary", "reuse")
DIMENSION_LABELS = dict(zip(DIMENSIONS, ("长期保持", "记忆调用", "动态更新", "相近区分", "边界识别", "任务复用")))
ASSERTION_TYPES = {"response_value", "response_absent", "memory_absent", "artifact_json"}


def parse_json(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError('non-finite JSON number: ' + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def relative_path(value: str) -> PurePosixPath:
    p = PurePosixPath(value)
    if not value or p.is_absolute() or ".." in p.parts or "\\" in value or "\x00" in value:
        raise ValueError("path must be a confined relative POSIX path")
    return p


def validate_dataset(data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError('dataset must be an object')
    if data.get("schema") != SCHEMA:
        raise ValueError("unsupported dataset schema")
    if not isinstance(data.get('dataset_id'), str) or not data['dataset_id']:
        raise ValueError('dataset_id is required')
    if type(data.get('seed')) is not int or not isinstance(data.get('provenance'), dict):
        raise ValueError('seed and provenance are required')
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("dataset must contain cases")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get('stratum'), str):
            raise ValueError('case object and stratum are required')
        cid = case.get("id", "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", cid) or cid in seen:
            raise ValueError("case id invalid or duplicated")
        seen.add(cid)
        if case.get("dimension") not in DIMENSIONS:
            raise ValueError("unknown memory dimension")
        facts = case.get('facts')
        if not isinstance(facts, list):
            raise ValueError('case facts must be a list')
        for fact in facts:
            if not isinstance(fact, dict) or 'value' not in fact:
                raise ValueError('fact requires a value')
            if not all(isinstance(fact.get(k), str) and fact[k] for k in ('subject', 'key')):
                raise ValueError('fact subject and key are required')
            if fact.get('policy') not in {'retain', 'session_only', 'sensitive', 'risk', 'noise'}:
                raise ValueError('unknown fact retention policy')
            if type(fact.get('revision')) is not int or fact['revision'] < 1:
                raise ValueError('fact revision must be a positive integer')
        phases = case.get("phases", [])
        if not isinstance(phases, list) or not phases:
            raise ValueError('case phases must be a non-empty list')
        ids = set()
        for phase in phases:
            if not isinstance(phase, dict):
                raise ValueError('phase must be an object')
            if not isinstance(phase.get("message"), str) or not phase["message"]:
                raise ValueError("phase message required")
            if phase.get("kind") not in {"write", "distract", "update", "query", "action"}:
                raise ValueError("phase kind invalid")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", phase.get("id", "")) or phase["id"] in ids:
                raise ValueError("phase id invalid or duplicated")
            if not isinstance(phase.get("session"), str) or not phase["session"]:
                raise ValueError("phase session required")
            ids.add(phase["id"])
        assertions = case.get("assertions", [])
        if not isinstance(assertions, list) or not assertions:
            raise ValueError("case requires assertions")
        assertion_ids = set()
        for rule in assertions:
            if not isinstance(rule, dict):
                raise ValueError('assertion must be an object')
            if rule.get("type") not in ASSERTION_TYPES or rule.get("phase") not in ids:
                raise ValueError("assertion type or phase invalid")
            if not rule.get("id") or rule["id"] in assertion_ids:
                raise ValueError("assertion id invalid or duplicated")
            assertion_ids.add(rule["id"])
            if rule["type"] in {"response_value", "artifact_json"} and "expected" not in rule:
                raise ValueError("positive assertion needs an oracle")
            if rule.get('field', 'answer') != 'answer':
                raise ValueError('v1 response rules use the answer field')
            if rule["type"] == "artifact_json":
                relative_path(rule["path"])
            if rule["type"] in {"memory_absent", "response_absent"}:
                if not isinstance(rule.get("forbidden"), list) or not rule["forbidden"]:
                    raise ValueError("negative assertion needs forbidden values")
                if not all(isinstance(v, str) and v for v in rule['forbidden']):
                    raise ValueError('forbidden values must be non-empty strings')
        if case.get("synthetic") is not True:
            raise ValueError("current distribution requires explicit synthetic provenance")
    canonical(data)


def adapter_request(case: dict, phase: dict, *, session_id: str, workspace: str) -> dict:
    """Whitelisted request, deliberately independent of facts and scoring rules."""
    return {"schema": "kmb.request/v1", "case_id": case["id"], "phase_id": phase["id"],
            "kind": phase["kind"], "session_id": session_id, "message": phase["message"],
            "workspace": workspace}
