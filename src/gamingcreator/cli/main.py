import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Never

from gamingcreator import __version__
from gamingcreator.application.inputs import AnalyzeInput, prepare_analyze
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.local_files import LocalInputReader


class CliParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise AppError("input.arguments", "参数格式错误，请使用 --help 查看命令。", ExitCode.INPUT)


def _parser() -> CliParser:
    parser = CliParser(prog="gamingcreator", description="本地游戏素材分析与检索开发工具")
    parser.add_argument("--version", action="version", version=f"gamingcreator {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="分析本地视频（处理链路待实现）")
    analyze.add_argument("video", type=Path)
    analyze.add_argument("--project", type=Path, required=True)
    analyze.add_argument("--config", type=Path)
    analyze.add_argument("--max-cost-cny")
    analyze.add_argument("--resume")
    search = commands.add_parser("search", help="查询时间线（检索链路待实现）")
    search.add_argument("query")
    search.add_argument("--project", type=Path, required=True)
    search.add_argument("--run", required=True)
    search.add_argument("--top-k", type=int, default=10)
    search.add_argument("--format", choices=("json",), default="json")
    benchmark = commands.add_parser("benchmark", help="执行人工标签评测（待实现）")
    benchmark.add_argument("--input", type=Path, required=True)
    benchmark.add_argument("--project", type=Path, required=True)
    benchmark.add_argument("--output", type=Path, required=True)
    return parser


def _dispatch(args: argparse.Namespace) -> Never:
    if args.command == "analyze":
        prepare_analyze(
            AnalyzeInput(args.video, args.project, args.config, args.max_cost_cny, args.resume),
            LocalInputReader(),
        )
    elif args.command == "search" and (
        not args.query.strip() or not args.run.strip() or args.top_k <= 0
    ):
        raise AppError("input.search", "查询、运行 ID 与正数 top-k 均为必需。", ExitCode.INPUT)
    raise AppError(
        "feature.not_implemented",
        "处理链路尚未实现；本版本仅验证命令与输入合同。",
        ExitCode.ENVIRONMENT,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        _dispatch(args)
    except SystemExit as error:
        return int(error.code) if isinstance(error.code, int) else int(ExitCode.INPUT)
    except KeyboardInterrupt:
        failure = AppError("operation.cancelled", "操作已取消。", ExitCode.CANCELLED)
    except AppError as error:
        failure = error
    except Exception:
        failure = AppError(
            "environment.unexpected", "无法完成操作，请检查本地运行环境。", ExitCode.ENVIRONMENT
        )
    print(
        json.dumps(
            {"code": failure.code, "runId": None, "retryable": False, "message": failure.message},
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    return int(failure.exit_code)
