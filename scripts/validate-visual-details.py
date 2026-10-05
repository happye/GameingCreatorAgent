"""Freeze V4/V5 and resolution controls; paid requests require --execute.

This development experiment never supplies human labels or passes F006/F010.
"""

import argparse
import asyncio
import importlib.util
import json
import os
import sys
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import uuid4

from gamingcreator.application.budget import BudgetLedger
from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.providers import CancellationContext, VisionRequest
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import MediaPreprocessingResult
from gamingcreator.domain.models import EvidenceReference, SemanticEvent
from gamingcreator.domain.time import SourceInstant
from gamingcreator.infrastructure.deepseek_vision import (
    MODEL,
    PROMPT_VERSION_V4,
    PROMPT_VERSION_V5,
    SCHEMA_VERSION_V4,
    DeepSeekVisionProvider,
    _jpeg_width,
    vision_prompt_fingerprint,
)
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor, hash_file
from gamingcreator.infrastructure.http_transport import HttpxVisionTransport

_SPEC = importlib.util.spec_from_file_location(
    "visual_detail_pilot_shared", Path(__file__).with_name("validate-temporal-gameplay.py")
)
assert _SPEC is not None and _SPEC.loader is not None
shared = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = shared
_SPEC.loader.exec_module(shared)
OUTPUT_TOKENS = 4096
INPUT_TOKEN_CEILING = 1_000_000


@dataclass(frozen=True)
class DetailCase:
    case_id: str
    run_id: str
    prompt_version: str
    image_max_width: int
    frames: tuple[EvidenceReference, ...]
    expected: str


def _references(media: MediaPreprocessingResult) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            item.evidence_id,
            media.asset.media_id,
            "image",
            item.source_time,
            item.path,
            item.sha256,
            media.transform_version,
        )
        for item in media.images
    )


def make_cases(
    low: MediaPreprocessingResult,
    high: MediaPreprocessingResult,
    starts_us: list[int],
    low_run_id: str,
    high_run_id: str,
    detail_prompt: str = PROMPT_VERSION_V5,
) -> tuple[DetailCase, ...]:
    if detail_prompt not in (PROMPT_VERSION_V5, "phase0-vision-v6"):
        raise AppError("detail_pilot.prompt_version", "未支持该细节提示版本。", ExitCode.INPUT)
    if (
        low.asset.media_id != high.asset.media_id
        or low.asset.sha256 != high.asset.sha256
        or low.asset.duration_us != high.asset.duration_us
        or low.asset.origin_seconds != high.asset.origin_seconds
        or low.asset.streams != high.asset.streams
        or tuple(item.source_time for item in low.images)
        != tuple(item.source_time for item in high.images)
    ):
        raise AppError(
            "detail_pilot.source_alignment",
            "两组分辨率证据的原源身份或源时间不一致，已停止实验。",
            ExitCode.INPUT,
        )
    cases: list[DetailCase] = []
    for index, start in enumerate(starts_us):
        selected = tuple(
            tuple(
                item
                for item in _references(media)
                if isinstance(item.source_time, SourceInstant)
                and start <= item.source_time.time_us <= start + 4_000_000
            )
            for media in (low, high)
        )
        if any(len(frames) != 9 for frames in selected):
            raise AppError(
                "detail_pilot.window_frames",
                "每个四秒窗口必须包含九个真实采样帧；请选对齐的起点或其他窗口。",
                ExitCode.INPUT,
            )
        low_frames, high_frames = selected
        prefix = f"window-{index}"
        static = tuple(
            replace(
                item,
                artifact_path=high_frames[0].artifact_path,
                sha256=high_frames[0].sha256,
                transform_version="visual-detail-static-control-v1",
            )
            for item in high_frames
        )
        cases.extend(
            (
                DetailCase(
                    prefix + "-A",
                    low_run_id,
                    PROMPT_VERSION_V4,
                    512,
                    low_frames,
                    "legacy_prompt_baseline",
                ),
                DetailCase(
                    prefix + "-B",
                    low_run_id,
                    detail_prompt,
                    512,
                    low_frames,
                    "same_frames_prompt_control",
                ),
                DetailCase(
                    prefix + "-C",
                    high_run_id,
                    detail_prompt,
                    1280,
                    high_frames,
                    "same_source_instants_resolution_control",
                ),
                DetailCase(
                    prefix + "-static-C",
                    high_run_id,
                    detail_prompt,
                    1280,
                    static,
                    "no_observed_temporal_action",
                ),
                DetailCase(
                    prefix + "-reversed-C",
                    high_run_id,
                    detail_prompt,
                    1280,
                    high_frames[::-1],
                    "provider.input_without_send",
                ),
            )
        )
    return tuple(cases)


def image_dimensions(path: Path) -> tuple[int, int]:
    """Read bounded JPEG dimensions using the provider's framing validation."""
    data = path.read_bytes()
    width = _jpeg_width(data)
    position = 2
    while position + 4 <= len(data):
        while data[position] == 255:
            position += 1
        marker = data[position]
        position += 1
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue
        length = int.from_bytes(data[position : position + 2], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return width, int.from_bytes(data[position + 3 : position + 5], "big")
        position += length
    raise ValueError("JPEG dimensions unavailable.")


def frame_record(item: EvidenceReference, output: Path) -> dict[str, object]:
    assert isinstance(item.source_time, SourceInstant)
    if hash_file(item.artifact_path) != item.sha256:
        raise AppError("detail_pilot.image_hash", "图片证据内容已变化。", ExitCode.INPUT)
    width, height = image_dimensions(item.artifact_path)
    return {
        "evidenceId": item.evidence_id,
        "sourceUs": item.source_time.time_us,
        "durationUs": item.source_time.duration_us,
        "artifact": str(item.artifact_path.relative_to(output)),
        "sha256": item.sha256,
        "transformVersion": item.transform_version,
        "width": width,
        "height": height,
        "bytes": item.artifact_path.stat().st_size,
    }


async def run_pilot(
    repository: Path,
    video: Path,
    output: Path,
    starts_us: list[int],
    max_cost_cny: Decimal = Decimal(5),
    request_limit: int = 8,
    execute: bool = False,
    detail_prompt: str = PROMPT_VERSION_V5,
) -> dict[str, Any]:
    repository, output = repository.resolve(), output.resolve()
    if not output.is_relative_to(repository / "artifacts"):
        raise AppError("detail_pilot.output", "输出必须在项目 artifacts/ 内。", ExitCode.INPUT)
    if not starts_us or any(type(start) is not int or start < 0 for start in starts_us):
        raise AppError("detail_pilot.window_start", "至少需要一个非负窗口起点。", ExitCode.INPUT)
    budget = BudgetLedger(max_cost_cny, request_limit, request_limit * 9)
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise AppError(
            "detail_pilot.output_exists", "输出目录已存在，请使用独立目录。", ExitCode.INPUT
        ) from None
    recorder = shared.JsonInvocationRecorder(output / "invocations.json")
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "qualityGate": None,
        "humanLabels": None,
        "status": "preprocessing",
        "executed": execute,
        "cases": [],
        "errorCode": None,
    }
    destination = output / "report.json"
    shared.write_json(destination, report)
    try:
        run_id, low_run_id, high_run_id = uuid4().hex, uuid4().hex, uuid4().hex
        processor = FfmpegMediaProcessor(repository)
        asset = await processor.probe(video, CancellationContext(run_id, 180))
        variants = []
        for width, variant_run in ((512, low_run_id), (1280, high_run_id)):
            variants.append(
                await processor.preprocess(
                    video,
                    output / f"media-{width}",
                    SamplingParameters(
                        Fraction(1, 2), width, (asset.duration_us + 499_999) // 500_000 + 1
                    ),
                    CancellationContext(variant_run, 300),
                )
            )
        cases = make_cases(
            variants[0], variants[1], starts_us, low_run_id, high_run_id, detail_prompt
        )
        frozen = {
            "schemaVersion": 1,
            "experiment": "visual-details-development-abc-v1",
            "frozenAtUtc": datetime.now(UTC).isoformat(),
            "runId": run_id,
            "sourceSha256": variants[0].asset.sha256,
            "sourceDurationUs": variants[0].asset.duration_us,
            "mediaId": variants[0].asset.media_id,
            "sourceClockOriginSeconds": str(variants[0].asset.origin_seconds),
            "preprocessingVariants": [
                {
                    "runId": variant_run,
                    "imageMaxWidth": width,
                    "manifest": str(media.manifest_path.relative_to(output)),
                    "manifestSha256": hash_file(media.manifest_path),
                    "transformVersion": media.transform_version,
                    "processorVersion": media.processor_version,
                }
                for media, width, variant_run in zip(
                    variants, (512, 1280), (low_run_id, high_run_id), strict=True
                )
            ],
            "samplingIntervalSeconds": "1/2",
            "requestedWindowStartsUs": starts_us,
            "requestedModel": MODEL,
            "responseSchema": SCHEMA_VERSION_V4,
            "inputTokenCeiling": INPUT_TOKEN_CEILING,
            "maxOutputTokens": OUTPUT_TOKENS,
            "priceSnapshot": asdict(DEEPSEEK_FLASH_20261004),
            "maxCostCny": str(max_cost_cny),
            "requestLimit": request_limit,
            "qualityGate": None,
            "humanLabels": None,
            "limitations": [
                "Development windows are not an independent human-labelled benchmark.",
                "Cross-resolution evidence retains source instants; image hashes may differ.",
                "Widths are upper bounds; smaller source images are not enlarged.",
                "Static control replaces pixels while retaining original observation times.",
                "Reversed references test input order, not reversed-action understanding.",
            ],
            "cases": [
                {
                    "id": case.case_id,
                    "runId": case.run_id,
                    "promptVersion": case.prompt_version,
                    "promptSha256": vision_prompt_fingerprint(case.prompt_version),
                    "responseSchema": SCHEMA_VERSION_V4,
                    "imageMaxWidth": case.image_max_width,
                    "imageDetail": "original"
                    if case.prompt_version in (PROMPT_VERSION_V5, "phase0-vision-v6")
                    else None,
                    "expected": case.expected,
                    "selectedFrames": [frame_record(item, output) for item in case.frames],
                }
                for case in cases
            ],
        }
        manifest = output / "frozen-manifest.json"
        shared.write_json(manifest, frozen)
        report.update(
            status="frozen",
            manifestSha256=hash_file(manifest),
            runId=run_id,
            sourceSha256=variants[0].asset.sha256,
            sourceDurationUs=variants[0].asset.duration_us,
        )
        shared.write_json(destination, report)
        if not execute:
            return report
        if "DEEPSEEK_API_KEY" not in os.environ:
            raise AppError("provider.auth", "当前进程未配置 API 凭据。", ExitCode.PROVIDER)
        provider = DeepSeekVisionProvider(
            HttpxVisionTransport(),
            budget,
            None,
            recorder,
            price_snapshot=DEEPSEEK_FLASH_20261004,
            input_token_ceiling=INPUT_TOKEN_CEILING,
        )
        report["status"] = "running"
        shared.write_json(destination, report)
        for case in cases:
            before = budget.requests
            result = await provider.analyze(
                VisionRequest(
                    case.run_id,
                    case.frames,
                    case.prompt_version,
                    SCHEMA_VERSION_V4,
                    OUTPUT_TOKENS,
                    stage_id=case.case_id,
                ),
                CancellationContext(case.run_id, 90),
            )
            events: tuple[SemanticEvent, ...] = result.output or ()
            control = None
            if case.case_id.endswith("-static-C"):
                control = len(events) == 0 and result.error is None
            elif case.case_id.endswith("-reversed-C"):
                control = (
                    result.error is not None
                    and result.error.code == "provider.input"
                    and budget.requests == before
                )
            case_report = {
                "id": case.case_id,
                "runId": case.run_id,
                "promptVersion": case.prompt_version,
                "imageMaxWidth": case.image_max_width,
                "selectedFrames": [frame_record(item, output) for item in case.frames],
                "status": result.status.value,
                "errorCode": None if result.error is None else result.error.code,
                "metadata": asdict(result.metadata),
                "events": [asdict(event) for event in events],
                "temporalControlPassed": control,
            }
            report["cases"].append(case_report)
            report["cost"] = shared.cost_summary(recorder, budget)
            shared.write_json(output / f"{case.case_id}.json", case_report)
            shared.write_json(destination, report)
        failed_cases = sum(
            case["temporalControlPassed"] is False
            or (case["errorCode"] is not None and not case["id"].endswith("-reversed-C"))
            for case in report["cases"]
        )
        report["failedCases"] = failed_cases
        report["status"] = "completed_with_failures" if failed_cases else "completed"
        return report
    except AppError as error:
        report.update(status="failed", errorCode=error.code)
        raise
    except asyncio.CancelledError:
        report.update(status="interrupted", errorCode="provider.cancelled")
        raise
    except (OSError, ValueError):
        report.update(status="failed", errorCode="detail_pilot.local")
        raise AppError(
            "detail_pilot.local", "本地处理失败；报告已保留。", ExitCode.ENVIRONMENT
        ) from None
    finally:
        report["cost"] = shared.cost_summary(recorder, budget)
        shared.write_json(destination, report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window-start", type=Decimal, action="append", required=True)
    parser.add_argument("--max-cost-cny", type=Decimal, default=Decimal(5))
    parser.add_argument("--request-limit", type=int, default=8)
    parser.add_argument(
        "--detail-prompt",
        choices=[PROMPT_VERSION_V5, "phase0-vision-v6"],
        default=PROMPT_VERSION_V5,
    )
    parser.add_argument("--execute", action="store_true", help="Allow billed API requests")
    args = parser.parse_args()
    if any(not start.is_finite() or start < 0 for start in args.window_start):
        parser.error("Window starts must be finite and nonnegative.")
    try:
        report = asyncio.run(
            run_pilot(
                Path(__file__).resolve().parents[1],
                args.video.resolve(),
                args.output,
                [int(start * 1_000_000) for start in args.window_start],
                args.max_cost_cny,
                args.request_limit,
                args.execute,
                args.detail_prompt,
            )
        )
        print(json.dumps({"report": str(args.output / "report.json"), "status": report["status"]}))
        if report["status"] == "completed_with_failures":
            return int(
                ExitCode.BUDGET
                if any(str(case["errorCode"]).startswith("budget.") for case in report["cases"])
                else ExitCode.PROVIDER
            )
        return 0
    except AppError as error:
        print(json.dumps({"code": error.code, "message": error.message}), file=sys.stderr)
        return int(error.exit_code)
    except ValueError:
        parser.error("Budget and request limits must be positive finite values.")
    except KeyboardInterrupt:
        return 130
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
