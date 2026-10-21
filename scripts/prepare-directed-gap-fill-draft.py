"""Write an inert directed gap-fill proposal draft from coverage; never call a model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gamingcreator.application.directed_gap_fill import (
    write_directed_gap_fill_proposal_draft,
)
from gamingcreator.domain.errors import AppError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "从 analysis_coverage.json 生成未冻结／未授权的定向补窗提案草稿到输出目录。"
            "不调用模型、不启动 launcher、不代选选项 B。"
        )
    )
    parser.add_argument(
        "--coverage",
        type=Path,
        required=True,
        help="analysis_coverage.json 路径",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="输出目录（建议放在已忽略的 artifacts/ 下）",
    )
    parser.add_argument(
        "--stage",
        action="append",
        dest="stages",
        default=None,
        help="可选：仅包含指定 rejected stageId（可重复）；默认全部 rejected",
    )
    parser.add_argument(
        "--max-additional-cost-cny",
        default=None,
        help="可选费用上限占位（写入草稿仍不授权）",
    )
    parser.add_argument(
        "--diagnosis-dir",
        type=Path,
        default=None,
        help="可选同帧诊断包目录（默认 artifacts/coverage-gap-diagnosis-20261021）",
    )
    parser.add_argument(
        "--docs-report",
        type=Path,
        default=None,
        help="可选仓库诊断报告路径（默认 docs/exec-plans/report-2026-10-21-coverage-gap-diagnosis.md）",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="可选仓库根（解析相对诊断／报告路径；默认当前工作目录）",
    )
    args = parser.parse_args(argv)
    try:
        receipt = write_directed_gap_fill_proposal_draft(
            args.coverage,
            args.output,
            proposed_stage_ids=args.stages,
            maximum_additional_cost_cny=args.max_additional_cost_cny,
            diagnosis_dir=args.diagnosis_dir,
            docs_report=args.docs_report,
            repo_root=args.repo_root,
        )
    except AppError as error:
        print(error.message, file=sys.stderr)
        return int(error.exit_code)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
