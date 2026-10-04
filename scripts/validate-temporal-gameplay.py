"""Freeze a source-clock A/B pilot; paid requests require explicit --execute.

This diagnostic is not a human-labelled benchmark and never passes F006.
"""

import argparse
import asyncio
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
from gamingcreator.application.providers import (
    CancellationContext,
    InvocationMetadata,
    VisionRequest,
)
from gamingcreator.application.storage import InvocationStatus, StoredInvocation
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import MediaPreprocessingResult
from gamingcreator.domain.models import EvidenceReference, SemanticEvent
from gamingcreator.domain.time import SourceInstant
from gamingcreator.infrastructure.deepseek_vision import (
    MODEL,
    PROMPT_VERSION_V2,
    SCHEMA_VERSION,
    DeepSeekVisionProvider,
    vision_prompt_fingerprint,
)
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor, hash_file
from gamingcreator.infrastructure.http_transport import HttpxVisionTransport

PROMPT_V3 = "phase0-vision-v3"  # Implemented by the provider owner, not duplicated here.
PROMPT_V4 = "phase0-vision-v4"
OUTPUT_TOKENS = 4096
INPUT_TOKEN_CEILING = 1_000_000


def response_schema(prompt_version: str) -> str:
    return "temporal-actions-v1" if prompt_version == PROMPT_V4 else SCHEMA_VERSION


def write_json(path: Path, value: object) -> None:
    """Replace one complete JSON snapshot; a crash cannot leave a partial record."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class JsonInvocationRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: list[StoredInvocation] = []
        self._save()

    def _save(self) -> None:
        write_json(self.path, [asdict(record) for record in self.records])

    async def begin_invocation(
        self,
        invocation_id: str,
        run_id: str,
        stage_id: str,
        logical_request_id: str,
        metadata: InvocationMetadata,
    ) -> None:
        self.records.append(
            StoredInvocation(
                invocation_id,
                run_id,
                stage_id,
                logical_request_id,
                InvocationStatus.RUNNING,
                metadata,
                None,
            )
        )
        self._save()

    async def finish_invocation(
        self,
        invocation_id: str,
        status: InvocationStatus,
        metadata: InvocationMetadata,
        error_code: str | None = None,
    ) -> None:
        for index, record in enumerate(self.records):
            if record.invocation_id == invocation_id:
                self.records[index] = replace(
                    record, status=status, metadata=metadata, error_code=error_code
                )
                self._save()
                return
        raise ValueError("Cannot finish an invocation without its durable start record.")


@dataclass(frozen=True)
class PilotCase:
    case_id: str
    prompt_version: str
    frames: tuple[EvidenceReference, ...]
    expected: str


def make_cases(
    media: MediaPreprocessingResult,
    starts_us: list[int],
    temporal_prompt: str = PROMPT_V3,
    same_frame_control: bool = False,
) -> tuple[PilotCase, ...]:
    references = tuple(
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
    cases: list[PilotCase] = []
    for index, start in enumerate(starts_us):
        # Include the last observation at +4 s, retaining its real decoder timestamp.
        frames = tuple(
            item
            for item in references
            if isinstance(item.source_time, SourceInstant)
            and start <= item.source_time.time_us <= start + 4_000_000
        )
        if len(frames) != 9:
            raise AppError(
                "pilot.window_frames",
                "每个四秒窗口必须包含九个真实采样帧；请选对齐的起点或其他窗口。",
                ExitCode.INPUT,
            )
        prefix = f"window-{index}"
        cases.extend(
            (
                PilotCase(prefix + "-A", PROMPT_VERSION_V2, frames[::2], "development_observation"),
                PilotCase(prefix + "-B", temporal_prompt, frames, "development_observation"),
            )
        )
        if same_frame_control:
            cases.append(
                PilotCase(prefix + "-C", temporal_prompt, frames[::2], "same_frames_prompt_control")
            )
    first = cases[1].frames
    static = tuple(
        replace(
            item,
            artifact_path=first[0].artifact_path,
            sha256=first[0].sha256,
            transform_version="temporal-static-control-v1",
        )
        for item in first
    )
    return tuple(cases) + (
        PilotCase("static-B", temporal_prompt, static, "no_observed_temporal_action"),
        PilotCase("reversed-order-B", temporal_prompt, first[::-1], "provider.input_without_send"),
    )


def frame_record(item: EvidenceReference, output: Path) -> dict[str, object]:
    assert isinstance(item.source_time, SourceInstant)
    return {
        "evidenceId": item.evidence_id,
        "sourceUs": item.source_time.time_us,
        "durationUs": item.source_time.duration_us,
        "artifact": str(item.artifact_path.relative_to(output)),
        "sha256": item.sha256,
        "transformVersion": item.transform_version,
    }


def prompt_hash(version: str) -> str | None:
    try:
        return vision_prompt_fingerprint(version)
    except ValueError:
        return None


def cost_summary(recorder: JsonInvocationRecorder, budget: BudgetLedger) -> dict[str, object]:
    unknown = sum(record.metadata.usage.cost_cny is None for record in recorder.records)
    return {
        "attemptCount": len(recorder.records),
        "knownApiCostCny": str(budget.known_cost_cny),
        "totalApiCostCny": None if unknown else str(budget.known_cost_cny),
        "unknownCostAttempts": unknown,
        "reservedCny": str(budget.reserved_cny),
        "committedCny": str(budget.committed_cny),
        "requestCount": budget.requests,
        "inputFrames": budget.frames,
        "billingConfirmed": False,
    }


async def run_pilot(
    repository: Path,
    video: Path,
    output: Path,
    starts_us: list[int],
    max_cost_cny: Decimal,
    request_limit: int,
    execute: bool,
    temporal_prompt: str = PROMPT_V3,
    same_frame_control: bool = False,
) -> dict[str, Any]:
    repository, output = repository.resolve(), output.resolve()
    if not output.is_relative_to(repository / "artifacts"):
        raise AppError("pilot.output", "实验输出必须在项目 artifacts/ 内。", ExitCode.INPUT)
    if not starts_us or any(start < 0 for start in starts_us):
        raise AppError("pilot.window_start", "至少需要一个非负窗口起点。", ExitCode.INPUT)
    try:
        budget = BudgetLedger(max_cost_cny, request_limit, request_limit * 9)
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise AppError(
            "pilot.output_exists", "输出目录已存在，请为新实验指定独立目录。", ExitCode.INPUT
        ) from None
    recorder = JsonInvocationRecorder(output / "invocations.json")
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "qualityGate": None,
        "status": "preprocessing",
        "executed": execute,
        "cases": [],
        "errorCode": None,
    }
    destination = output / "report.json"
    write_json(destination, report)
    try:
        run_id = uuid4().hex
        processor = FfmpegMediaProcessor(repository)
        asset = await processor.probe(video, CancellationContext(run_id, 180))
        media = await processor.preprocess(
            video,
            output / "media",
            SamplingParameters(Fraction(1, 2), 512, (asset.duration_us + 499_999) // 500_000 + 1),
            CancellationContext(run_id, 300),
        )
        cases = make_cases(media, starts_us, temporal_prompt, same_frame_control)
        frozen = {
            "schemaVersion": 1,
            "experiment": "temporal-gameplay-development-ab",
            "frozenAtUtc": datetime.now(UTC).isoformat(),
            "runId": run_id,
            "sourceSha256": media.asset.sha256,
            "sourceDurationUs": media.asset.duration_us,
            "mediaId": media.asset.media_id,
            "sourceClockOriginSeconds": str(media.asset.origin_seconds),
            "preprocessingManifestSha256": hash_file(media.manifest_path),
            "samplingIntervalSeconds": "1/2",
            "imageMaxWidth": 512,
            "requestedWindowStartsUs": starts_us,
            "requestedModel": MODEL,
            "responseSchemas": {
                case.prompt_version: response_schema(case.prompt_version) for case in cases
            },
            "inputTokenCeiling": INPUT_TOKEN_CEILING,
            "maxOutputTokens": OUTPUT_TOKENS,
            "priceVersion": DEEPSEEK_FLASH_20261004.version,
            "maxCostCny": str(max_cost_cny),
            "requestLimit": request_limit,
            "qualityGate": None,
            "humanLabels": None,
            "limitations": [
                "Development windows are not an independent human-labelled benchmark.",
                "Static control replaces pixels, retaining original evidence IDs and source times.",
                "Reversed source order is an input-contract control, not a reversed-action label.",
            ],
            "cases": [
                {
                    "id": case.case_id,
                    "promptVersion": case.prompt_version,
                    "promptSha256": prompt_hash(case.prompt_version),
                    "responseSchema": response_schema(case.prompt_version),
                    "expected": case.expected,
                    "selectedFrames": [frame_record(item, output) for item in case.frames],
                }
                for case in cases
            ],
        }
        manifest = output / "frozen-manifest.json"
        write_json(manifest, frozen)  # Always durable before any paid request.
        report.update(
            status="frozen",
            manifestSha256=hash_file(manifest),
            runId=run_id,
            sourceSha256=media.asset.sha256,
            sourceDurationUs=media.asset.duration_us,
        )
        write_json(destination, report)
        if not execute:
            return report
        if prompt_hash(temporal_prompt) is None:
            raise AppError(
                "pilot.provider_version", "尚未集成该时序 Provider。", ExitCode.ENVIRONMENT
            )
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
        for case in cases:
            before = budget.requests
            result = await provider.analyze(
                VisionRequest(
                    run_id,
                    case.frames,
                    case.prompt_version,
                    response_schema(case.prompt_version),
                    OUTPUT_TOKENS,
                    stage_id=case.case_id,
                ),
                CancellationContext(run_id, 90),
            )
            events: tuple[SemanticEvent, ...] = result.output or ()
            report["cases"].append(
                {
                    "id": case.case_id,
                    "promptVersion": case.prompt_version,
                    "selectedFrames": [frame_record(item, output) for item in case.frames],
                    "status": result.status.value,
                    "errorCode": None if result.error is None else result.error.code,
                    "metadata": asdict(result.metadata),
                    "events": [asdict(event) for event in events],
                    "temporalControlPassed": (
                        len(events) == 0 and result.error is None
                        if case.case_id == "static-B"
                        else result.error is not None
                        and result.error.code == "provider.input"
                        and budget.requests == before
                        if case.case_id == "reversed-order-B"
                        else None
                    ),
                }
            )
            report["cost"] = cost_summary(recorder, budget)
            write_json(destination, report)
        failed_cases = sum(
            case["temporalControlPassed"] is False
            or (case["errorCode"] is not None and case["id"] != "reversed-order-B")
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
        report.update(status="failed", errorCode="pilot.local")
        raise AppError(
            "pilot.local", "实验本地处理失败；查看保留的报告。", ExitCode.ENVIRONMENT
        ) from None
    finally:
        report["cost"] = cost_summary(recorder, budget)
        write_json(destination, report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window-start", type=Decimal, action="append", required=True)
    parser.add_argument("--max-cost-cny", type=Decimal, default=Decimal(5))
    parser.add_argument("--request-limit", type=int, default=12)
    parser.add_argument("--temporal-prompt", choices=[PROMPT_V3, PROMPT_V4], default=PROMPT_V4)
    parser.add_argument("--same-frame-control", action="store_true")
    parser.add_argument(
        "--execute", action="store_true", help="Explicitly allow billed API requests"
    )
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
                args.temporal_prompt,
                args.same_frame_control,
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
