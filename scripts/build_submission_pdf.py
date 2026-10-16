#!/usr/bin/env python3
"""Build the Chinese submission overview without changing benchmark evidence."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import shutil
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Paragraph, Preformatted, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/SUBMISSION_OVERVIEW_20261016.md"
OUTPUT = ROOT / "output/pdf"
REPORT = ROOT / "results/full48-verified-report-20261016"
AUDIT = ROOT / "results/full48-audit-20261016"
TARGET_REPORT = ROOT / "results/openkylin-episode-report-20261016"
TARGET_AUDIT = ROOT / "results/openkylin-audit-20261016"
CORE_SHA = "009a6472cd96347aa121669cb19daebb7a59a5be367943525cdc25e102cebb30"
DATA_SHA = "5ae280f9b16c8afabadaee29886c4a9b2c5ee1863284316a241d87c1bf69e2bb"
PILOT_SHA = "48c56ba68a8d43a8f1c59eb5985726a70ebb53d5ff02fe2154a02e9b4d25995a"
AXES = ("persistence", "retrieval", "update", "discrimination", "boundary", "reuse")
PAGE_COUNT = 14
LABELS = ("长期保持", "记忆调用", "动态更新", "相近区分", "边界识别", "任务复用")
W, H = A4
MARGIN = 43.0
WIDTH = W - 2 * MARGIN
INK = colors.HexColor("#202D35")
MUTED = colors.HexColor("#5A6972")
TEAL = colors.HexColor("#00766A")
CORAL = colors.HexColor("#C35B46")
BLUE = colors.HexColor("#397BA6")
RULE = colors.HexColor("#D7E1E5")
PALE = colors.HexColor("#F0F5F6")
WHITE = colors.white

FONT_CANDIDATES = (
    ("macOS STHeitiSC", "/System/Library/Fonts/STHeiti Light.ttc", 1,
     "/System/Library/Fonts/STHeiti Medium.ttc", 1),
    ("WenQuanYi Micro Hei", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0, None, 0),
    ("WenQuanYi Zen Hei", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0, None, 0),
    ("AR PL UKai CN", "/usr/share/fonts/truetype/arphic/ukai.ttc", 0, None, 0),
    ("WenQuanYi Micro Hei", "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc", 0, None, 0),
    ("WenQuanYi Zen Hei", "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc", 0, None, 0),
)
FONT_SETUP_HELP = """
这些字体依赖仅用于 PDF 创作，核心 kmb 不受影响，也不需要安装 ReportLab 或字体。
openKylin/Debian 系常用安装示例（以本机软件源可用包为准）：
  sudo apt update
  sudo apt install fonts-wqy-microhei fonts-wqy-zenhei fonts-arphic-ukai
PDF 创作环境另需 reportlab、pypdf；--render 还需 Pillow 与 poppler-utils。
可显式指定已安装的中文 TrueType 字体并先预检，例如：
  python3 scripts/build_submission_pdf.py --check-fonts \\
    --font-regular /usr/share/fonts/truetype/wqy/wqy-microhei.ttc \\
    --font-regular-index 0
--font-bold / --font-bold-index 可另选粗体；未指定粗体时复用所选常规字体并在回执注明。
TTC 的子字体序号从 0 开始；Mac 自动模式选 STHeitiSC 的 1，WQY / UKai 候选选 0。
仅接受 TrueType 轮廓；不自动选 Noto CFF，也不按 .ttc/.otf 扩展名推定可用性。
"""

DEFAULT_PLATFORM = {
    "schema": "kmb.submission-platform/v1",
    "system": "openKylin 2.0 SP2 (nile)，内核 6.6.0-19-generic",
    "access_status": "KVM 虚拟机，真实 UKUI 私有 X11 会话",
    "acceptance_status": "目标平台增量任务验收完成；两端共 176 阶段正常结束，0 运行异常",
    "identity_receipt": "x86_64 / Python 3.12.2",
    "framework_receipt": "OpenClaw 2026.3.8 (3caab92) / Hermes 0.8.0 (2026.4.8)，OpenAI SDK 2.31.0",
    "model_receipt": "同一 HTTPS Responses 入口，请求 gpt-6-sol，显式客户端推理设置 off",
    "regression_receipt": "完整 unittest 96 项通过，无跳过，162.003 s",
    "real_agent_receipt": "data/episodes-pilot-12.json；6 配对、12 案例、88 阶段，每端各 1 轮",
    "debian_receipt": "适配 KARE 系统的用户级一键安装已通过；Debian 包独立解包后启动成功，六种 fixture 各 6 案例/22 阶段校准通过（共 36 案例/132 阶段）。",
    "installation_demo_receipt": "真实 UKUI 录屏剪辑约 3 分 50 秒，配中文旁白与字幕；[公开发布页](https://github.com/yanchaomei/kylin-memory-bench/releases/tag/v0.2.0-oscc)提供视频与校验摘要",
    "evidence_refs": ["results/openkylin-episode-report-20261016/comparison.json",
                      "results/openkylin-audit-20261016/audit.json"],
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf8"))


def guarded_output(path):
    path = path.resolve()
    if not path.is_relative_to(OUTPUT.resolve()):
        raise ValueError("All generated artifacts and QA must stay under output/pdf")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path, value):
    guarded_output(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                              allow_nan=False) + "\n", encoding="utf8")


def load_evidence():
    audit = read_json(AUDIT / "audit.json")
    audit_manifest = read_json(AUDIT / "manifest.json")
    entry = next(item for item in audit_manifest["files"] if item["path"] == "audit.json")
    if (audit_manifest.get("schema") != "kmb.manifest/v1"
            or (AUDIT / "audit.json").stat().st_size != entry["bytes"]
            or sha(AUDIT / "audit.json") != entry["sha256"]):
        raise ValueError("Full-study audit receipt does not match its manifest")
    expected_trials = {f"{agent}/repeat-{repeat:03d}" for agent in ("Hermes-API", "OpenClaw-API")
                       for repeat in range(1, 4)}
    if (audit.get("schema") != "kmb.study-audit/v1"
            or audit.get("study_manifest") != {"ok": True, "errors": []}
            or audit.get("files_verified") != 12702 or audit.get("stage_count") != 2112
            or len(audit.get("runs", [])) != 6
            or {run["trial"] for run in audit["runs"]} != expected_trials
            or any(run.get("verified") is not True or run.get("scoring_fields_match") is not True
                   or run.get("phases") != 352 or run.get("cases") != 48 for run in audit["runs"])):
        raise ValueError("Full-study audit receipt is incomplete or differs from the documented study")
    manifest = read_json(REPORT / "manifest.json")
    entries = {item["path"]: item for item in manifest["files"]}
    selected_checks = {}
    for name in ("comparison.json", "reliability.json"):
        path = REPORT / name
        selected_checks[name] = path.stat().st_size == entries[name]["bytes"] and sha(path) == entries[name]["sha256"]
        if not selected_checks[name]:
            raise ValueError("Selected report does not match manifest: " + name)
    comparison = read_json(REPORT / "comparison.json")
    reliability = read_json(REPORT / "reliability.json")
    files = {p.name: sha(p) for p in sorted((ROOT / "kylin_memory_bench").glob("*.py"))}
    if len(files) != 14 or hashlib.sha256(canonical(files)).hexdigest() != CORE_SHA:
        raise ValueError("Expected frozen 14-module core fingerprint differs")
    data = read_json(ROOT / "data/episodes-test-48.json")
    if any(value != DATA_SHA for value in (
            comparison["dataset_sha256"], reliability["dataset_sha256"], hashlib.sha256(canonical(data)).hexdigest())):
        raise ValueError("Dataset fingerprint differs")
    agents = {a["name"]: a for a in comparison["agents"]}
    rel = {a["name"]: a for a in reliability["agents"]}
    expected = {
        "Hermes-API": {"success": [1, 1, 1, 11 / 12, .5, 1], "complete": 23,
                       "gain": 1, "pass3": 43 / 48, "coverage": 142 / 144,
                       "counts": [130, 12, 2]},
        "OpenClaw-API": {"success": [.875, 23 / 24, .75, 11 / 12, .5, 23 / 24],
                         "complete": 17, "gain": 50 / 51, "pass3": 34 / 48,
                         "coverage": 133 / 144, "counts": [119, 14, 11]},
    }
    metric_checks = []
    for name, e in expected.items():
        a, r = agents[name], rel[name]
        assert a["kind"] == "real" and a["repeats"] == r["repeats"] == 3
        for axis, v in zip(AXES, e["success"]):
            assert math.isclose(a["dimensions"][axis]["success_rate"], v, abs_tol=1e-12)
        total = sum(sum(a["dimensions"][d]["total_per_run"]) for d in AXES)
        passed = sum(sum(a["dimensions"][d]["passed_per_run"]) for d in AXES)
        valid = round(total * r["scorable_fraction"])
        assert [passed, valid - passed, total - valid] == e["counts"]
        assert a["paired_summary"]["complete_pairs"] == e["complete"]
        assert math.isclose(a["paired_summary"]["mean_source_gain"], e["gain"])
        assert math.isclose(r["pass_power"]["3"], e["pass3"])
        assert math.isclose(r["scorable_fraction"], e["coverage"])
        for env in a["environments"]:
            assert env["os_release"]["ID"] == "ubuntu" and env["machine"] == "x86_64"
            assert env["openkylin"] is False
        assert all(x["model"] == "gpt-6-sol" and x["reasoning_effort"] == "off" for x in a["configurations"])
        metric_checks.append({"agent": name, "pass_fail_unknown": e["counts"], "checked": True})
    contrast = reliability["system_contrasts"][0]
    assert contrast["operational"]["episodes"] == 24
    assert contrast["operational"]["exact_two_sided_p"] == .0078125
    assert contrast["complete_only"]["episodes"] == 16
    assert contrast["complete_only"]["exact_two_sided_p"] == 1
    assert len(data["cases"]) == 48 and sum(len(c["phases"]) for c in data["cases"]) == 352
    return comparison, reliability, {
        "core_sha256": CORE_SHA, "core_files": files, "dataset_sha256": DATA_SHA,
        "selected_report_manifest_checks": selected_checks, "metric_checks": metric_checks,
        "full_study_audit_receipt": {"path": str(AUDIT / "audit.json"), "sha256": sha(AUDIT / "audit.json"),
                                     "manifest_checked": True, "files_verified": audit["files_verified"],
                                     "runs_verified": len(audit["runs"]), "stage_count": audit["stage_count"]},
        "scope": "Verified aggregate report files, current core/dataset fingerprints and read-back of the completed full-study audit receipt; the PDF build does not rerun the archive audit",
    }


def load_target_evidence():
    checks = {}
    for folder, names in ((TARGET_REPORT, ("comparison.json", "reliability.json")),
                          (TARGET_AUDIT, ("audit.json",))):
        manifest = read_json(folder / "manifest.json")
        if manifest.get("schema") != "kmb.manifest/v1":
            raise ValueError("Invalid target-platform manifest")
        entries = {item["path"]: item for item in manifest["files"]}
        for name in names:
            path = folder / name
            ok = path.stat().st_size == entries[name]["bytes"] and sha(path) == entries[name]["sha256"]
            checks[str(path.relative_to(ROOT))] = ok
            if not ok:
                raise ValueError("Target-platform input does not match manifest: " + str(path))
    comparison = read_json(TARGET_REPORT / "comparison.json")
    reliability = read_json(TARGET_REPORT / "reliability.json")
    audit = read_json(TARGET_AUDIT / "audit.json")
    data = read_json(ROOT / "data/episodes-pilot-12.json")
    if (comparison.get("dataset_sha256") != PILOT_SHA or reliability.get("dataset_sha256") != PILOT_SHA
            or hashlib.sha256(canonical(data)).hexdigest() != PILOT_SHA
            or len(data["cases"]) != 12 or sum(len(c["phases"]) for c in data["cases"]) != 88):
        raise ValueError("Target-platform pilot dataset differs from the frozen 12-case input")
    if (audit.get("schema") != "kmb.target-audit/v1" or audit.get("manifest") != {"ok": True, "errors": []}
            or audit.get("stage_errors") != 0 or audit.get("regression_tests") != 96
            or audit.get("regression_seconds") != 162.003 or audit.get("kernel") != "6.6.0-19-generic"):
        raise ValueError("Target-platform audit is incomplete or differs from documented acceptance")
    agents = {a["name"]: a for a in comparison["agents"]}
    audited = {a["agent"]: a for a in audit["runs"]}
    versions = {"Hermes-API": "Hermes Agent v0.8.0 (2026.4.8)", "OpenClaw-API": "OpenClaw 2026.3.8 (3caab92)"}
    if set(agents) != {"Hermes-API", "OpenClaw-API"} or set(audited) != set(agents):
        raise ValueError("Target-platform acceptance must contain the two declared native agents")
    for name, agent in agents.items():
        row = audited[name]
        if (agent["kind"] != "real" or agent["repeats"] != 1 or agent["run_ids"] != [row["run_id"]]
                or [row.get(k) for k in ("passed", "failed", "unknown", "phases")] != [11, 1, 0, 88]
                or row.get("openkylin") is not True or agent["versions"] != [versions[name]]
                or row.get("version") != versions[name]):
            raise ValueError("Target-platform run counts or identity differ: " + name)
        for axis, expected in zip(AXES, (1, 1, 1, 1, .5, 1)):
            metric = agent["dimensions"][axis]
            if (metric["success_rate"] != expected or metric["coverage"] != 1
                    or metric["passed_per_run"] != [int(2 * expected)] or metric["total_per_run"] != [2]):
                raise ValueError("Target-platform dimension differs: " + name + "/" + axis)
        env = agent["environments"][0]
        if (env.get("openkylin") is not True or env["os_release"].get("ID") != "openkylin"
                or env.get("python") != "3.12.2" or env.get("machine") != "x86_64"
                or env.get("release") != "6.6.0-19-generic" or env.get("desktop") != "UKUI"
                or env.get("display_present") is not True):
            raise ValueError("Target-platform environment differs: " + name)
        config = agent["configurations"][0]
        if (config.get("model") != "gpt-6-sol" or config.get("reasoning_effort") != "off"
                or not config.get("base_url", "").startswith("https://")):
            raise ValueError("Target-platform model configuration differs: " + name)
        pairs = agent["paired_summary"]
        if (pairs["independent_pairs"] != 6 or pairs["complete_pairs"] != 6
                or pairs["mean_source_gain"] != 1 or pairs["bootstrap_95"] != [1, 1]
                or pairs["provided_target_rate"] != 1 or pairs["withheld_target_rate"] != 0):
            raise ValueError("Target-platform paired results differ: " + name)
    if len({a["configurations"][0]["base_url"] for a in agents.values()}) != 1:
        raise ValueError("Target-platform agents must use the same HTTPS endpoint")
    return {"comparison": comparison, "audit": audit, "checks": checks,
            "dataset_sha256": PILOT_SHA, "scope": "Separate 12-case, one-repeat target acceptance; never pooled with Ubuntu 48-case study"}


class PdfFontError(ValueError):
    """An actionable PDF-authoring font error, unrelated to benchmark execution."""


def true_type_face(path, index):
    if index < 0:
        raise PdfFontError(f"TTC 子字体序号必须大于等于 0：{index}")
    if not path.is_file():
        raise PdfFontError(f"字体文件不存在或不是普通文件：{path}")
    with path.open("rb") as file:
        signature = file.read(4)
        count = 1
        if signature == b"ttcf":
            header = file.read(8)
            if len(header) != 8:
                raise PdfFontError(f"TTC 文件头不完整：{path}")
            count = struct.unpack(">I", header[4:8])[0]
            if not 1 <= count <= 4096 or 12 + 4 * count > path.stat().st_size:
                raise PdfFontError(f"TTC 子字体目录损坏：{path}")
            if index >= count:
                raise PdfFontError(f"TTC 子字体序号 {index} 越界，可选范围 0-{count - 1}：{path}")
            file.seek(12 + 4 * index)
            offset = struct.unpack(">I", file.read(4))[0]
            file.seek(offset)
            signature = file.read(4)
        elif index != 0:
            raise PdfFontError(f"非 TTC 字体只能使用子字体序号 0：{path}")
    if signature == b"OTTO":
        raise PdfFontError(f"子字体 {index} 使用 CFF/OTTO 轮廓，不适合此 ReportLab TrueType 构建：{path}")
    if signature not in (b"\x00\x01\x00\x00", b"true"):
        raise PdfFontError(f"不是可用的 TrueType 字体或文件已损坏：{path}")
    return count


def load_pdf_font(name, path, index, required):
    path = Path(path).expanduser().resolve()
    try:
        count = true_type_face(path, index)
        font = TTFont(name, str(path), subfontIndex=index)
    except PdfFontError:
        raise
    except (TTFError, ValueError, OSError, IndexError, struct.error) as exc:
        raise PdfFontError(f"无法解析字体 {path}（子字体 {index}）：{exc}") from exc
    missing = sorted(code for code in required if not font.face.charToGlyph.get(code))
    if missing:
        example = ", ".join(f"U+{code:04X} {chr(code)}" for code in missing[:8])
        raise PdfFontError(f"字体缺少本文所需的 {len(missing)} 个字形（{example}）：{path}")
    meta = {"path": str(path), "subfont_index": index, "collection_faces": count,
            "face_name": font.face.name.decode("utf8", errors="replace"),
            "outline": "TrueType", "required_glyphs": len(required), "missing_glyphs": 0}
    return font, meta


def register_fonts(args):
    required = {ord(ch) for ch in SOURCE.read_text(encoding="utf8")
                if not ch.isspace() and ord(ch) >= 32}
    failures = []
    candidates = FONT_CANDIDATES
    if args.font_regular is not None:
        candidates = (("explicit", str(args.font_regular), 0, None, 0),)
    for label, regular, regular_index, bold, bold_index in candidates:
        if args.font_regular_index is not None:
            regular_index = args.font_regular_index
        if args.font_bold is not None:
            bold = str(args.font_bold)
            bold_index = 0
        if bold is None:
            bold, bold_index = regular, regular_index
        if args.font_bold_index is not None:
            bold_index = args.font_bold_index
        if args.font_regular is None and not Path(regular).is_file():
            failures.append("字体文件不存在：" + regular)
            continue
        try:
            normal, normal_meta = load_pdf_font("CJK", regular, regular_index, required)
        except PdfFontError as exc:
            if args.font_regular is not None or args.font_regular_index is not None:
                raise
            failures.append(str(exc))
            continue
        try:
            heavy, heavy_meta = load_pdf_font("CJK-Bold", bold, bold_index, required)
        except PdfFontError as exc:
            if args.font_bold is not None or args.font_bold_index is not None:
                raise
            failures.append(str(exc))
            continue
        break
    else:
        raise PdfFontError("未找到可用的中文 TrueType 字库。\n尝试结果：\n- " + "\n- ".join(failures))
    pdfmetrics.registerFont(normal)
    pdfmetrics.registerFont(heavy)
    pdfmetrics.registerFontFamily("CJK", normal="CJK", bold="CJK-Bold", italic="CJK", boldItalic="CJK-Bold")
    reused = normal_meta["path"] == heavy_meta["path"] and normal_meta["subfont_index"] == heavy_meta["subfont_index"]
    return {"regular": normal_meta["path"], "bold": heavy_meta["path"], "embedded": True,
            "selection": label, "regular_face": normal_meta, "bold_face": heavy_meta,
            "bold_reuses_regular": reused,
            "notes": ["未提供独立粗体，标题复用常规字体；未伪称独立粗体轮廓。"] if reused else [],
            "skipped_candidates": failures}


def verify_document_values(comparison, reliability):
    source = SOURCE.read_text(encoding="utf8")
    rows = [[v.strip() for v in line.strip().strip("|").split("|")]
            for line in source.splitlines() if line.startswith("|")]
    agents = {a["name"]: a for a in comparison["agents"]}
    rel = {a["name"]: a for a in reliability["agents"]}
    checks = []
    for axis, label in zip(AXES, LABELS):
        expected = [label]
        for name in ("Hermes-API", "OpenClaw-API"):
            expected.extend(f'{agents[name]["dimensions"][axis][key] * 100:.3f}%'
                            for key in ("success_rate", "coverage"))
        if expected not in rows:
            raise ValueError("Document dimension table differs from report: " + label)
        checks.append("dimensions/" + axis)
    for name in ("Hermes-API", "OpenClaw-API"):
        a, r = agents[name], rel[name]
        total = r["cases"] * r["repeats"]
        passed = sum(r["successes_per_case"].values())
        scored = round(total * r["scorable_fraction"])
        counts = f'{passed} / {scored - passed} / {total - scored}（{total} 次）'
        expected = [name.removesuffix("-API"), counts]
        expected.extend(f'{100 * r["pass_power"][str(k)]:.3f}%' for k in (1, 2, 3))
        expected.append(f'{100 * r["repeat_state_agreement"]:.3f}%')
        if expected not in rows:
            raise ValueError("Document reliability table differs from report: " + name)
        p = a["paired_summary"]
        expected = [name.removesuffix("-API"),
                    f'{p["complete_pairs"]}/{p["independent_pairs"]}（{100 * p["complete_pair_coverage"]:.3f}%）',
                    f'{100 * p["provided_target_rate"]:.3f}%', f'{100 * p["withheld_target_rate"]:.3f}%',
                    f'+{100 * p["mean_source_gain"]:.3f}<br/>[{100 * p["bootstrap_95"][0]:.3f}, {100 * p["bootstrap_95"][1]:.3f}]']
        if expected not in rows:
            raise ValueError("Document paired table differs from report: " + name)
        checks.append("reliability-and-pairs/" + name)
    samples = [json.loads(x) for x in re.findall(r"```json\n(.*?)\n```", source, re.DOTALL)]
    data = read_json(ROOT / "data/episodes-test-48.json")
    example = next(c for c in data["cases"] if c["id"] == "episode-88ad1945ff8583b1")
    if samples[:2] != [example["facts"][2], example["assertions"][0]]:
        raise ValueError("Document JSON examples differ from frozen dataset")
    for sample in samples[2:]:
        if sample.get("schema") == "kmb.request/v1":
            required = {"schema", "case_id", "phase_id", "kind", "session_id", "message", "workspace"}
            if set(sample) != required or not all(isinstance(value, str) for value in sample.values()):
                raise ValueError("Document request example differs from adapter whitelist")
        elif isinstance(sample.get("response"), str):
            if set(sample) - {"response", "session_id"} or not isinstance(json.loads(sample["response"]), dict):
                raise ValueError("Document bridge example is not a structured response")
        else:
            raise ValueError("Additional document JSON example is not a registered interface example")
    return {"result_tables_match_reports": True, "json_examples_match_dataset": True,
            "checked_rows": checks}


def styles():
    base = dict(fontName="CJK", textColor=INK, wordWrap="CJK", alignment=TA_LEFT,
                splitLongWords=True, allowWidows=0, allowOrphans=0)
    return {
        "title": ParagraphStyle("title", fontSize=23, leading=31, fontName="CJK-Bold", **{k: v for k, v in base.items() if k != "fontName"}),
        "cover": ParagraphStyle("cover", fontSize=34, leading=43, fontName="CJK-Bold", **{k: v for k, v in base.items() if k != "fontName"}),
        "heading": ParagraphStyle("heading", fontSize=13, leading=19, fontName="CJK-Bold", **{k: v for k, v in base.items() if k != "fontName"}),
        "body": ParagraphStyle("body", fontSize=10.1, leading=16.2, **base),
        "quote": ParagraphStyle("quote", fontSize=10.4, leading=17, textColor=TEAL, **{k: v for k, v in base.items() if k != "textColor"}),
        "small": ParagraphStyle("small", fontSize=8.7, leading=13.4, **base),
        "cell": ParagraphStyle("cell", fontSize=9.0, leading=13.1, **base),
        "cellsmall": ParagraphStyle("cellsmall", fontSize=8.3, leading=12.2, **base),
        "code": ParagraphStyle("code", fontSize=8.2, leading=11.7, **base),
        "figure": ParagraphStyle("figure", fontSize=9, leading=13.5, **base),
        "caption": ParagraphStyle("caption", fontSize=8.0, leading=11.5, textColor=MUTED,
                                  **{k: v for k, v in base.items() if k != "textColor"}),
    }


def inline(text):
    text = html.escape(text)
    text = text.replace("&lt;br/&gt;", "<br/>")
    text = re.sub(r"\[([^\]]+)\]\((https://[^\s)]+)\)", r'<link href="\2" color="#27627B">\1</link>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r'<b>\1</b>', text)
    text = re.sub(r"`(.+?)`", r'<font color="#27627B">\1</font>', text)
    return text


class CodeBlock(Flowable):
    def __init__(self, text, style):
        super().__init__()
        self.text = text
        self.style = style
        self.inner = Preformatted(text, style, dedent=0)

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        for line in self.text.splitlines():
            if pdfmetrics.stringWidth(line, self.style.fontName, self.style.fontSize) > availWidth - 22:
                raise ValueError("Code line too wide: " + line)
        _, h = self.inner.wrap(availWidth - 22, availHeight)
        self.height = h + 19
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(PALE)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        c.setFillColor(BLUE)
        c.rect(0, 0, 2, self.height, fill=1, stroke=0)
        self.inner.drawOn(c, 11, 9)


class Diagram(Flowable):
    HEIGHTS = {"overview": 116, "architecture": 280, "incremental": 208,
               "paired": 154, "integrity": 130, "dimensions": 228}

    def __init__(self, kind, comparison, st):
        super().__init__()
        if kind not in self.HEIGHTS:
            raise ValueError("Unknown diagram: " + kind)
        self.kind, self.comparison, self.st = kind, comparison, st
        self.width, self.height = WIDTH, self.HEIGHTS[kind]

    def wrap(self, aw, ah):
        return self.width, self.height

    def text(self, x, top, width, text, *, color=INK, bold=False, size=9, leading=13.2):
        style = ParagraphStyle("fig-local", parent=self.st["figure"], textColor=color,
                               fontName="CJK-Bold" if bold else "CJK", fontSize=size, leading=leading)
        p = Paragraph(inline(text).replace("\n", "<br/>"), style)
        _, h = p.wrap(width, self.height)
        if top - h < -1 or x < 0 or x + width > self.width + 1:
            raise ValueError("Diagram text out of bounds: " + text)
        p.drawOn(self.canv, x, top - h)
        return h

    def box(self, x, y, w, h, title, body, color=TEAL, fill=PALE):
        c = self.canv
        c.setFillColor(fill)
        c.setStrokeColor(RULE)
        c.setLineWidth(.65)
        c.rect(x, y, w, h, fill=1, stroke=1)
        c.setFillColor(color)
        c.rect(x, y + h - 3, w, 3, fill=1, stroke=0)
        th = self.text(x + 10, y + h - 12, w - 20, title, bold=True, color=color, size=10)
        bh = self.text(x + 10, y + h - 18 - th, w - 20, body, size=8.7, leading=12.4)
        if th + bh + 22 > h:
            raise ValueError("Diagram box text too tall: " + title)

    def arrow(self, x1, y1, x2, y2, color=MUTED):
        c = self.canv
        c.setStrokeColor(color)
        c.setFillColor(color)
        c.setLineWidth(1)
        c.line(x1, y1, x2, y2)
        angle = math.atan2(y2 - y1, x2 - x1)
        p = c.beginPath()
        p.moveTo(x2, y2)
        for offset in (-.48, .48):
            p.lineTo(x2 - 5 * math.cos(angle + offset), y2 - 5 * math.sin(angle + offset))
        p.close()
        c.drawPath(p, fill=1, stroke=0)

    def draw(self):
        getattr(self, "draw_" + self.kind)()

    def draw_overview(self):
        boxes = [("冻结任务", "六维事实与阶段\n目标真值留在评测器", TEAL),
                 ("原生运行", "独立工作区\n新进程、新会话", BLUE),
                 ("四路证据", "回复、存储、轨迹\n实际任务产物", CORAL),
                 ("可重算判定", "成功、失败、未知\n六维与配对统计", TEAL)]
        gap = 16
        bw = (self.width - gap * 3) / 4
        for i, (title, body, color) in enumerate(boxes):
            x = i * (bw + gap)
            self.box(x, 25, bw, 83, title, body, color)
            if i < 3:
                self.arrow(x + bw + 2, 66, x + bw + gap - 2, 66)
        self.text(0, 17, self.width, "图 1  从输入到结果的证据链；评测器不接管参评系统的记忆机制。", size=8, color=MUTED)

    def draw_architecture(self):
        col = (self.width - 28) / 3
        xs = [0, col + 14, 2 * col + 28]
        for x, label, color in zip(xs, ("01  评测器", "02  参评系统", "03  结果与核查"), (TEAL, BLUE, CORAL)):
            self.text(x, 274, col, label, bold=True, color=color, size=10)
        self.box(xs[0], 168, col, 82, "冻结生成器", "seed / facts / policy\n阶段与两臂共同目标\n完整再生成校验", TEAL)
        self.box(xs[1], 168, col, 82, "原生适配与运行", "OpenClaw / Hermes\nJSON 标准输入/输出桥接\n仅接收当前请求", BLUE)
        self.box(xs[2], 168, col, 82, "四路证据归档", "回复 + 长期存储\n原生轨迹 + 实际产物\n每阶段独立文件", CORAL)
        self.arrow(xs[0] + col + 1, 210, xs[1] - 2, 210, TEAL)
        self.arrow(xs[1] + col + 1, 210, xs[2] - 2, 210, BLUE)
        self.box(xs[0], 58, col, 85, "真值与规则", "assertions / objective\n不随请求转发\n不根据回答修改", TEAL)
        self.box(xs[1], 58, col, 85, "框架自身记忆", "原生写入、更新与调用\nprofile + workspace\n案例内持久、案例间隔离", BLUE)
        self.box(xs[2], 58, col, 85, "核验、评分与报告", "manifest + 证据关联\n离线重算 / 六维 / 配对\nJSON / CSV / HTML / SVG", CORAL)
        self.arrow(xs[1] + col / 2, 165, xs[1] + col / 2, 146, BLUE)
        self.arrow(xs[2] + col / 2, 165, xs[2] + col / 2, 146, CORAL)
        self.canv.setStrokeColor(TEAL)
        self.canv.line(xs[0] + col / 2, 58, xs[0] + col / 2, 48)
        self.arrow(xs[0] + col / 2, 48, xs[2] + col / 2, 48, TEAL)
        self.arrow(xs[2] + col / 2, 48, xs[2] + col / 2, 56, TEAL)
        self.text(0, 32, self.width, "图 2  真值留在评测器；原生框架负责自己的记忆；最终报告可返回阶段证据。", size=8, color=MUTED)

    def timeline(self, y, label, items, color):
        self.text(0, y + 54, self.width, label, bold=True, color=color, size=10)
        gap = 10
        bw = (self.width - gap * (len(items) - 1)) / len(items)
        for i, (title, body) in enumerate(items):
            x = i * (bw + gap)
            self.box(x, y - 20, bw, 59, title, body, color)
            if i < len(items) - 1:
                self.arrow(x + bw + 1, y + 9, x + bw + gap - 1, y + 9, color)

    def draw_incremental(self):
        self.timeline(143, "更新链：依据版本，不让迟到旧值覆盖新值", [
            ("写入 v1", "learn"), ("4 次干扰", "独立新会话"), ("更新 v2/v3", "revision 递增"),
            ("迟到 v1", "delayed"), ("最终查询", "应返回 v3")], TEAL)
        self.timeline(48, "行动链：检查点与最终交接文件分别核对", [
            ("初始交接", "路径 + 交接码"), ("第一次行动", "checkpoint.json"), ("4 次干扰", "其他办公资料"),
            ("版本反馈", "新交接码"), ("第二次行动", "handover.json")], BLUE)
        self.text(0, 13, self.width, "图 3  两类代表性 episode；反馈预先冻结，箭头不表示延续聊天上下文。", size=8, color=MUTED)

    def draw_paired(self):
        bw = 174
        self.box(0, 81, bw, 65, "provided / 提供资料", "目标实体各版本 + 其他资料", TEAL)
        self.box(0, 8, bw, 65, "withheld / 扣除资料", "等条数无关实体 + 其他资料", CORAL)
        x = bw + 35
        self.box(x, 45, 148, 68, "同一查询或行动", "文字逐字一致\n两臂状态独立", BLUE)
        self.arrow(bw + 2, 112, x - 3, 89, TEAL)
        self.arrow(bw + 2, 42, x - 3, 66, CORAL)
        rx = x + 171
        self.arrow(x + 151, 79, rx - 5, 79, BLUE)
        self.text(rx, 109, self.width - rx, "同一正向目标", bold=True, size=9)
        self.text(rx, 87, self.width - rx, "是否达成？\n是否按政策行动？\n两项分开记。", size=8.7)

    def draw_integrity(self):
        bw = (self.width - 30) / 3
        for i, (title, body, color) in enumerate([
                ("01  文件核对", "manifest\n大小 / SHA-256 / 文件清单", TEAL),
                ("02  关联核对", "dataset -> run -> phase\nrequest / stdout / artifact", BLUE),
                ("03  离线重算", "规则评分 -> 六维与配对\n不信任松散 score 文件", CORAL)]):
            x = i * (bw + 15)
            self.box(x, 32, bw, 88, title, body, color)
            if i < 2:
                self.arrow(x + bw + 2, 76, x + bw + 13, 76)
        self.text(0, 21, self.width, "图 4  完整性是证据链的前置条件，不等同于任务成功或第三方认证。", size=8, color=MUTED)

    def draw_dimensions(self):
        c = self.canv
        agents = {a["name"]: a for a in self.comparison["agents"]}
        left, plotw = 78, self.width - 132
        for v in (0, .25, .5, .75, 1):
            x = left + v * plotw
            c.setStrokeColor(RULE)
            c.setLineWidth(.5)
            c.line(x, 28, x, 202)
            self.text(x - 9, 20, 31, f"{v * 100:.0f}%", size=7.6, color=MUTED)
        for row, (axis, label) in enumerate(zip(AXES, LABELS)):
            y = 188 - row * 29
            self.text(0, y + 8, 73, label, size=9.2)
            for offset, name, color in [(6, "Hermes-API", TEAL), (-6, "OpenClaw-API", CORAL)]:
                v = agents[name]["dimensions"][axis]["success_rate"]
                c.setFillColor(color)
                c.rect(left, y + offset - 3.2, v * plotw, 6.4, fill=1, stroke=0)
                self.text(left + v * plotw + 4, y + offset + 4.2,
                          self.width - (left + v * plotw + 4), f"{v * 100:.1f}", color=color, size=7.8, leading=10)
        for x, name, color in ((left, "Hermes", TEAL), (left + 100, "OpenClaw", CORAL)):
            c.setFillColor(color)
            c.rect(x, 216, 12, 5, fill=1, stroke=0)
            self.text(x + 18, 224, 90, name, size=8.7, color=color)


def make_table(rows, st):
    rows = [r for r in rows if not re.fullmatch(r"[\s|:\-]+", r)]
    data = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in rows]
    n = len(data[0])
    if any(len(row) != n for row in data):
        raise ValueError("Malformed Markdown table")
    header = " ".join(data[0])
    if n == 2:
        fractions = (.29, .71)
    elif n == 3:
        fractions = (.22, .38, .40)
        if "关键入口" in header:
            fractions = (.21, .35, .44)
    elif n == 4:
        fractions = (.28, .16, .21, .35)
        if "比较集合" in header:
            fractions = (.40, .16, .29, .15)
    elif n == 5:
        fractions = (.23, .18, .18, .18, .23)
        if "维度" in header:
            fractions = (.20, .21, .18, .23, .18)
    elif n == 6:
        fractions = (.15, .29, .14, .14, .14, .14)
    else:
        fractions = tuple(1 / n for _ in range(n))
    total = sum(fractions)
    widths = [WIDTH * f / total for f in fractions]
    cellstyle = st["cellsmall"] if n >= 5 else st["cell"]
    parsed = []
    for i, row in enumerate(data):
        cells = []
        for j, cell in enumerate(row):
            content = inline(cell)
            # Keep identifiers whole when a delimiter offers a better line break.
            if ("关键入口" in header or "机器标签" in header) and re.fullmatch(r"[a-z_]+(?:[、]| / )[a-z_、 /]+", cell):
                pieces = re.split(r"、| / ", cell)
                too_wide = pdfmetrics.stringWidth(cell, cellstyle.fontName, cellstyle.fontSize) > widths[j] - 14
                if too_wide:
                    content = "<br/>".join(inline(p) for p in pieces)
            if i == 0:
                content = "<b>" + content + "</b>"
            cells.append(Paragraph(content, cellstyle))
        parsed.append(cells)
    table = Table(parsed, colWidths=widths, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), .8, TEAL),
        ("LINEBELOW", (0, 1), (-1, -1), .4, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def platform_markdown(platform, target):
    agents = {a["name"]: a for a in target["comparison"]["agents"]}
    audited = {a["agent"]: a for a in target["audit"]["runs"]}
    names = ("Hermes-API", "OpenClaw-API")
    counts = [f'{audited[n]["passed"]} / {audited[n]["failed"]} / {audited[n]["unknown"]}' for n in names]
    phases = [f'{audited[n]["phases"]} / 0' for n in names]
    gains = [f'+{100 * agents[n]["paired_summary"]["mean_source_gain"]:.0f} pp；[100, 100] pp' for n in names]
    return "\n\n".join([
        "**环境：**" + platform["system"] + "；" + platform["identity_receipt"] + "；" + platform["access_status"] + "。",
        "**固定配置：**" + platform["framework_receipt"] + "；" + platform["model_receipt"] + "。",
        "**冻结输入：**" + platform["real_agent_receipt"] + "；共 176 阶段全部正常完成，0 运行异常。",
        "\n".join([
            "| 指标（每端各一轮） | Hermes | OpenClaw |", "|---|---|---|",
            f"| 通过 / 失败 / 未知 | {counts[0]} | {counts[1]} |",
            f"| 完成 / 异常阶段 | {phases[0]} | {phases[1]} |",
            "| 覆盖率 / 完整配对 | 100% / 6 对全齐 | 100% / 6 对全齐 |",
            f"| 资料收益 / 95% 区间 | {gains[0]} | {gains[1]} |",
        ]),
        "**六维成功率（两端一致）：**长期保持 100%、记忆调用 100%、动态更新 100%、相近区分 100%、边界识别 50%、任务复用 100%。",
        "**唯一失败类型：**边界提供臂把未知项目串用为合法项目值，属于错误关联、未正确拒答，**不是禁止标记泄漏**。区间只描述当前 6 个配对，不代表未见任务没有不确定性。",
        "先导集 SHA-256：`" + PILOT_SHA + "`",
    ])


def parse_page(text, st, comparison, page_num):
    lines = text.splitlines()
    blocks = []
    sources = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("<!-- source:"):
            sources.append(line.removeprefix("<!-- source:").removesuffix("-->").strip())
            i += 1
            continue
        if line.startswith("<!--"):
            i += 1
            continue
        if line.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            blocks.append(("code", CodeBlock("\n".join(code), st["code"]), 9))
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            blocks.append(("table", make_table(rows, st), 10))
            continue
        figure = re.fullmatch(r"\{\{figure:(\w+)\}\}", line)
        if figure:
            blocks.append(("figure:" + figure[1], Diagram(figure[1], comparison, st), 8))
            i += 1
            continue
        if line.startswith("# "):
            blocks.append(("title", Paragraph(inline(line[2:]), st["cover" if page_num == 1 else "title"]), 14))
        elif line.startswith("## "):
            blocks.append(("heading", Paragraph(inline(line[3:]), st["heading"]), 7))
        elif line.startswith("> "):
            blocks.append(("quote", Paragraph(inline(line[2:]), st["quote"]), 12))
        elif line.startswith("- ") or re.match(r"\d+\. ", line):
            blocks.append(("list", Paragraph(inline(line if not line.startswith("- ") else "-  " + line[2:]), st["body"]), 6))
        else:
            para = [line]
            while i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith(("#", "|", "```", "<!--", "{{", ">", "- ")):
                if re.match(r"\d+\. ", lines[i + 1]):
                    break
                i += 1
                para.append(lines[i].strip())
            blocks.append(("paragraph", Paragraph(inline(" ".join(para)), st["body"]), 9))
        i += 1
    return blocks, sources


def draw_page_frame(canvas, page, total):
    canvas.setFillColor(WHITE)
    canvas.rect(0, 0, W, H, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(MARGIN, H - 39, 28, 3, fill=1, stroke=0)
    canvas.setFillColor(MUTED)
    canvas.setFont("CJK", 8.0)
    canvas.drawString(MARGIN + 38, H - 39, "Kylin Memory Bench  /  OSCC openKylin 长期记忆 Benchmark")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(.55)
    canvas.line(MARGIN, 45, W - MARGIN, 45)
    canvas.setFillColor(MUTED)
    canvas.setFont("CJK", 7.6)
    canvas.drawString(MARGIN, 29, "作品介绍  |  v0.2.0  |  2026-10-16  |  Linux 研究与目标平台分别归档")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(W - MARGIN, 29, f"{page:02d} / {total:02d}")


def build_pdf(path, comparison, platform, target):
    st = styles()
    delivery = (platform["debian_receipt"] + "\n\n**工程回归：**" + platform["regression_receipt"]
                + "。\n\n**演示与源码：**" + platform["installation_demo_receipt"]
                + "。仓库：[yanchaomei/kylin-memory-bench](https://github.com/yanchaomei/kylin-memory-bench)。")
    source = (SOURCE.read_text(encoding="utf8")
              .replace("{{platform_facts}}", platform_markdown(platform, target))
              .replace("{{platform_delivery}}", delivery))
    parts = re.split(r"<!-- page:(\d{2}) -->", source)
    pages = list(zip(parts[1::2], parts[2::2]))
    if len(pages) != PAGE_COUNT or [int(p[0]) for p in pages] != list(range(1, PAGE_COUNT + 1)):
        raise ValueError(f"Expected {PAGE_COUNT} ordered document pages")
    canvas = Canvas(str(guarded_output(path)), pagesize=A4, pageCompression=1)
    canvas.setTitle("Kylin Memory Bench - OSCC openKylin 长期记忆 Benchmark 作品介绍")
    canvas.setAuthor("Kylin Memory Bench")
    canvas.setSubject("六维长期记忆评测、配对资料收益与可重算原生运行证据")
    layout = []
    for num, text in pages:
        pagenum = int(num)
        blocks, sources = parse_page(text, st, comparison, pagenum)
        draw_page_frame(canvas, pagenum, len(pages))
        source_para = Paragraph(inline("来源：" + " ".join(sources)), st["caption"])
        _, sh = source_para.wrap(WIDTH, H)
        bottom = 60 + sh + 9
        y = H - 65
        entries = []
        title = re.search(r"^# (.+)$", text, re.MULTILINE).group(1)
        canvas.bookmarkPage(f"page-{num}")
        canvas.addOutlineEntry(f"{num}  {title}", f"page-{num}", level=0)
        for kind, block, gap in blocks:
            if kind == "heading" and entries:
                y -= 3
            width, height = block.wrap(WIDTH, H)
            if y - height < bottom:
                raise ValueError(f"Page {num} overflow at {kind}: needs {height:.1f}, available {y - bottom:.1f}")
            block.drawOn(canvas, MARGIN, y - height)
            entries.append({"kind": kind, "bbox": [MARGIN, y - height, MARGIN + width, y]})
            y -= height + gap
        source_para.drawOn(canvas, MARGIN, 60)
        layout.append({"page": pagenum, "title": title, "content_bottom": round(y, 3),
                       "required_bottom": round(bottom, 3), "bottom_clearance": round(y + blocks[-1][2] - bottom, 3),
                       "blocks": entries, "sources": sources})
        canvas.showPage()
    canvas.save()
    return layout


def check_document(pdf, layout):
    from pypdf import PdfReader
    reader = PdfReader(str(pdf))
    text = "\n".join(p.extract_text() for p in reader.pages)
    checks = {
        f"page_count_{PAGE_COUNT}": len(reader.pages) == PAGE_COUNT,
        "no_replacement_characters": "\ufffd" not in text and "\u25a0" not in text,
        "all_content_blocks_fit": all(b["bottom_clearance"] >= 0 for b in layout),
        "no_template_markers": "{{" not in text,
        "paired_unit_boundary": "不是 288 个独立任务" in text,
        "linux_identity": "Ubuntu 24.04.1" in text,
        "openkylin_identity": "openKylin 2.0 SP2" in text,
        "matching_test_both_endpoints": "0.0078125" in text and "1.0000000" in text,
        "core_sha256_present": CORE_SHA in text.replace("\n", ""),
        "data_sha256_present": DATA_SHA in text.replace("\n", ""),
        "all_pages_have_sources": all("来源：" in p.extract_text() for p in reader.pages),
        f"outline_entries_{PAGE_COUNT}": len(reader.outline) == PAGE_COUNT,
        "full_linux_archive_audit_closed": "12,702" in text and "12,701" in text
            and "full48-audit-20261016/audit.json" in text.replace("\n", "")
            and "收回与完整性核验仍进行中" not in text,
        "rendered_text_glyphs_available": all(
            pdfmetrics.getFont(name).face.charToGlyph.get(ord(ch))
            for name in ("CJK", "CJK-Bold") for ch in set(text)
            if not ch.isspace() and ord(ch) >= 32),
        "target_pilot_hash_present": PILOT_SHA in text.replace("\n", ""),
        "target_not_in_progress": "正式评测运行中" not in text and "176 阶段，仍在运行" not in text,
        "target_boundary_not_leakage": "不是禁止标记泄漏" in text,
        "target_installation_scope": "用户级一键安装" in text
            and "Debian 包独立解包后启动成功" in text,
    }
    if not all(checks.values()):
        raise ValueError("PDF document checks failed: " + repr(checks))
    text_path = guarded_output(OUTPUT / "qa/submission_extracted_text.txt")
    text_path.write_text(text, encoding="utf8")
    return checks


def render_pages(pdf):
    from PIL import Image, ImageDraw
    tool = shutil.which("pdftoppm")
    if tool is None:
        raise RuntimeError("pdftoppm is required for visual QA")
    folder = OUTPUT / "qa/render"
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run([tool, "-r", "120", "-png", str(pdf), str(folder / "page")], check=True,
                   capture_output=True, text=True)
    paths = sorted(folder.glob("page-*.png"))
    if len(paths) != PAGE_COUNT:
        raise ValueError(f"Expected {PAGE_COUNT} rendered page images")
    sheets = []
    for start in range(0, len(paths), 4):
        group = paths[start:start + 4]
        sheet = Image.new("RGB", (1260, 1810), "#dfe6e9")
        draw = ImageDraw.Draw(sheet)
        for index, path in enumerate(group):
            page = Image.open(path).convert("RGB")
            page.thumbnail((590, 834))
            x = 25 + (index % 2) * 625
            y = 38 + (index // 2) * 890
            sheet.paste(page, (x, y))
            draw.text((x, y - 23), f"PAGE {start + index + 1:02d}", fill="#202d35")
        out = guarded_output(OUTPUT / f"qa/contact-sheet-{start // 4 + 1:02d}.png")
        sheet.save(out)
        sheets.append(str(out))
    return {"renderer": tool, "dpi": 120, "pages": [str(p) for p in paths], "contact_sheets": sheets}


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=FONT_SETUP_HELP,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUTPUT / "KylinMemoryBench_作品介绍_20261016.pdf")
    parser.add_argument("--platform-facts", type=Path, help="Optional evidence-backed target-platform facts JSON")
    parser.add_argument("--render", action="store_true", help="Render every page using pdftoppm and produce QA contact sheets")
    parser.add_argument("--font-regular", type=Path, help="Chinese TrueType font path; explicit files default to subfont 0")
    parser.add_argument("--font-bold", type=Path, help="Optional bold TrueType font path; defaults to selected regular font")
    parser.add_argument("--font-regular-index", type=int, help="Zero-based regular TTC subfont index (standalone TTF: 0)")
    parser.add_argument("--font-bold-index", type=int, help="Zero-based bold TTC subfont index (standalone TTF: 0)")
    parser.add_argument("--check-fonts", action="store_true", help="Check font format, TTC indices and document glyph coverage only; write no artifacts")
    args = parser.parse_args()
    try:
        fonts = register_fonts(args)
    except PdfFontError as exc:
        parser.exit(2, f"PDF 字体配置失败：{exc}\n{FONT_SETUP_HELP}")
    if args.check_fonts:
        print(json.dumps({"ok": True, "fonts": fonts}, ensure_ascii=False, indent=2))
        return
    comparison, reliability, evidence = load_evidence()
    target = load_target_evidence()
    document_values = verify_document_values(comparison, reliability)
    platform = dict(DEFAULT_PLATFORM)
    if args.platform_facts:
        supplied = read_json(args.platform_facts)
        if supplied.get("schema") != DEFAULT_PLATFORM["schema"]:
            raise ValueError("Unsupported platform facts schema")
        if set(supplied) - set(DEFAULT_PLATFORM):
            raise ValueError("Unknown platform facts fields")
        if supplied != DEFAULT_PLATFORM and not supplied.get("evidence_refs"):
            raise ValueError("Changed target-platform facts require evidence_refs")
        for ref in supplied.get("evidence_refs", []):
            path = Path(ref)
            if not path.is_absolute():
                path = ROOT / path
            if not path.is_file():
                raise ValueError("Platform evidence file is unavailable: " + ref)
        platform.update(supplied)
    write_json(OUTPUT / "qa/platform_facts_used.json", platform)
    if not args.platform_facts:
        write_json(OUTPUT / "platform_facts.json", platform)
    layout = build_pdf(args.out, comparison, platform, target)
    write_json(OUTPUT / "qa/layout.json", layout)
    checks = check_document(args.out, layout)
    render = render_pages(args.out) if args.render else None
    inputs = [SOURCE, Path(__file__), ROOT / "data/episodes-test-48.json", REPORT / "comparison.json",
              REPORT / "reliability.json", REPORT / "manifest.json", AUDIT / "audit.json", AUDIT / "manifest.json"]
    inputs.extend([TARGET_REPORT / "comparison.json", TARGET_REPORT / "reliability.json", TARGET_REPORT / "manifest.json",
                   TARGET_AUDIT / "audit.json", TARGET_AUDIT / "manifest.json", ROOT / "data/episodes-pilot-12.json"])
    inputs.extend(ROOT / p for p in ("docs/DESIGN.md", "docs/EPISODIC_PROTOCOL.md", "docs/CODE_GUIDE.md",
                                   "docs/TOPCONF_METHODS_20261009.md", "docs/RESULTS_V020_20261009.md",
                                   "docs/TEST_REPORT.md", "docs/LINUX_STUDY_20261009.md", "docs/DEPLOYMENT.md"))
    receipt = {
        "schema": "kmb.submission-pdf-qa/v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "pdf": str(args.out.resolve()), "pdf_sha256": sha(args.out), "pages": len(layout),
        "fonts": fonts, "checks": checks, "selected_evidence_checks": evidence,
        "document_value_checks": document_values,
        "target_evidence_checks": {k: v for k, v in target.items() if k not in ("comparison", "audit")},
        "input_hashes": {str(p.relative_to(ROOT)): sha(p) for p in inputs},
        "platform_facts": platform, "rendering": render,
        "visual_review": "Required: inspect all rendered pages; this field does not claim human/model visual review",
        "verification_boundary": "No remote/model work or benchmark rerun. The completed full raw-stage archive audit is represented by its checked receipt, not rerun by the PDF builder",
    }
    write_json(OUTPUT / "qa/build_receipt.json", receipt)
    print(json.dumps({"pdf": str(args.out.resolve()), "pages": len(layout), "sha256": receipt["pdf_sha256"],
                      "checks": checks, "rendered_pages": len(render["pages"]) if render else 0}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
