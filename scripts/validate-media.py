"""F002 developer validation; local processing only, never model/API requests."""

import argparse
import asyncio
import json
import sys
import time
import uuid
from fractions import Fraction
from pathlib import Path

from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor, hash_file


async def validate(
    sources: list[Path],
    repository: Path,
    *,
    max_frames: int = 1000,
    interval_ms: int = 1000,
    timeout_seconds: int = 180,
) -> Path:
    run_id = uuid.uuid4().hex
    output = repository / "artifacts" / "media-F002" / run_id
    processor = FfmpegMediaProcessor(repository)
    parameters = SamplingParameters(Fraction(interval_ms, 1000), max_frames=max_frames)
    cases = []
    for index, source in enumerate(sources):
        started = time.perf_counter()
        result = await processor.preprocess(
            source,
            output / str(index),
            parameters,
            CancellationContext(run_id, timeout_seconds),
        )
        audio = result.audio
        summary = {
            "source": str(source.relative_to(repository))
            if source.is_relative_to(repository)
            else source.name,
            "durationUs": result.asset.duration_us,
            "images": len(result.images),
            "audioSamples": None if audio is None else audio.sample_count,
            "audioDiscontinuities": None if audio is None else len(audio.discontinuity_offsets),
            "samplesBeyondDeclaredEndRemoved": None
            if audio is None or audio.decoded_sample_count is None
            else audio.decoded_sample_count - audio.sample_count,
            "elapsedSeconds": round(time.perf_counter() - started, 3),
            "sourceSha256": result.asset.sha256,
            "manifest": str(result.manifest_path.relative_to(repository)),
            "manifestSha256": hash_file(result.manifest_path),
        }
        cases.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    report = output / "validation.json"
    report.write_text(
        json.dumps(
            {
                "feature": "F002",
                "status": "completed",
                "samplingIntervalMs": interval_ms,
                "maxFrames": max_frames,
                "timeoutSeconds": timeout_seconds,
                "cases": cases,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return report


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Local F002 media validation")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--input", type=Path)
    selection.add_argument("--all-local", action="store_true")
    parser.add_argument("--max-frames", type=int, default=1000)
    parser.add_argument("--interval-ms", type=int, default=1000)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()
    if args.max_frames <= 0 or args.interval_ms <= 0 or args.timeout_seconds <= 0:
        parser.error("帧数上限、采样间隔和处理期限须为正整数。")
    sources = (
        sorted((repository / "GameVideos").rglob("*.mp4"))
        if args.all_local
        else [args.input.resolve()]
    )
    if not sources:
        print("No local videos found.", file=sys.stderr)
        return 2
    try:
        report = asyncio.run(
            validate(
                sources,
                repository,
                max_frames=args.max_frames,
                interval_ms=args.interval_ms,
                timeout_seconds=args.timeout_seconds,
            )
        )
        print(json.dumps({"report": str(report)}, ensure_ascii=False))
        return 0
    except AppError as error:
        print(
            json.dumps({"code": error.code, "message": error.message}, ensure_ascii=False),
            file=sys.stderr,
        )
        return int(error.exit_code)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
