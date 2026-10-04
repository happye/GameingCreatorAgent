from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

from gamingcreator.domain.errors import AppError, ExitCode


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    provider: str
    model: str
    max_requests: int
    max_input_frames: int
    schema_version: int = 1
    price_version: str | None = None
    sampling_interval_ms: int = 1000
    window_frames: int = 5
    window_overlap: int = 1
    max_output_tokens: int = 2048
    asr_language: str = "zh"


class InputReader(Protocol):
    def validate_video(self, path: Path) -> Path: ...

    def load_config(self, path: Path) -> AnalysisConfig: ...


@dataclass(frozen=True, slots=True)
class AnalyzeInput:
    video: Path
    project: Path
    config_path: Path | None
    max_cost_cny: str | None
    resume: str | None
    retry_uncertain: bool = False


@dataclass(frozen=True, slots=True)
class PreparedAnalyze:
    video: Path
    project: Path
    config: AnalysisConfig | None
    max_cost_cny: Decimal | None
    resume: str | None
    retry_uncertain: bool = False


def prepare_analyze(command: AnalyzeInput, reader: InputReader) -> PreparedAnalyze:
    video = reader.validate_video(command.video)
    if command.resume is not None:
        if not command.resume.strip() or command.config_path or command.max_cost_cny is not None:
            raise AppError(
                "input.resume", "续跑须提供运行 ID，且不得覆盖配置或预算。", ExitCode.INPUT
            )
        return PreparedAnalyze(
            video, command.project, None, None, command.resume, command.retry_uncertain
        )
    if command.retry_uncertain:
        raise AppError("input.resume", "重试未确认调用只适用于显式续跑。", ExitCode.INPUT)
    if command.config_path is None or command.max_cost_cny is None:
        raise AppError("input.analyze", "新分析须提供配置文件与正数费用上限。", ExitCode.INPUT)
    try:
        budget = Decimal(command.max_cost_cny)
    except InvalidOperation:
        budget = Decimal("NaN")
    if not budget.is_finite() or budget <= 0:
        raise AppError("input.budget", "费用上限必须是有限正数。", ExitCode.INPUT)
    config = reader.load_config(command.config_path)
    return PreparedAnalyze(video, command.project, config, budget, None)
