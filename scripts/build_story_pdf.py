#!/usr/bin/env python3
"""Render the R2 technical narrative without replacing the frozen first edition."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("kmb_submission_pdf", root / "scripts/build_submission_pdf.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = root / "docs/SUBMISSION_FULL_R2_20261016.md"
    source.write_text("\n\n".join((root / "docs" / name).read_text(encoding="utf8") for name in (
        "SUBMISSION_OVERVIEW_STORY_20261016.md", "SUBMISSION_MECHANISM_R2_20261016.md",
        "SUBMISSION_APPENDIX_R2_20261016.md")), encoding="utf8")
    module.SOURCE = source
    module.OUTPUT = root / "output/pdf/story-r2"
    module.PAGE_COUNT = 26
    original_diagram = module.Diagram
    from reportlab.platypus import Image

    def diagram(kind, comparison, style):
        if kind == "ai_overview":
            return Image(str(root / "assets/illustrations/long-term-memory-mechanisms.png"),
                         width=module.WIDTH, height=module.WIDTH * 2 / 3)
        return original_diagram(kind, comparison, style)

    module.Diagram = diagram
    module.DEFAULT_PLATFORM["installation_demo_receipt"] = (
        "真实 UKUI 录屏剪辑 3 分 51 秒，配中文旁白与字幕；"
        "[增强版发布页](https://github.com/yanchaomei/kylin-memory-bench/releases/tag/v0.2.0-oscc-r2)提供视频与校验摘要"
    )
    module.main()


if __name__ == "__main__":
    main()
