"""F004 developer evidence: real local media round-tripped by a second process.

Runs intentionally require only the media stage. No model, semantic event or
retrieval quality is measured; this utility makes no network/API requests.
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.storage import RunConfiguration
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


async def read_project(project: Path, run_ids: list[str]) -> list[dict[str, object]]:
    store = await SqliteTimelineStore.open(project, read_only=True)
    cases: list[dict[str, object]] = []
    try:
        for run_id in run_ids:
            timeline = await store.load_completed_timeline(run_id)
            media = await store.load_media_bundle(run_id)
            audio = media.audio
            cases.append(
                {
                    "runId": run_id,
                    "status": str(timeline.run.status),
                    "mediaId": media.asset.media_id,
                    "durationUs": media.asset.duration_us,
                    "images": len(media.images),
                    "evidence": len(timeline.evidence),
                    "audioFrames": None if audio is None else len(audio.frames),
                    "audioDiscontinuities": None
                    if audio is None
                    else len(audio.discontinuity_offsets),
                    "events": len(timeline.events),
                    "invocations": len(timeline.invocations),
                }
            )
    finally:
        await store.close()
    return cases


async def validate(sources: list[Path], repository: Path) -> Path:
    project = repository / "artifacts" / "storage-F004" / uuid.uuid4().hex
    store = await SqliteTimelineStore.open(project)
    processor = FfmpegMediaProcessor(repository)
    config = RunConfiguration(
        AnalysisConfig("none", "storage-media-only", 1, 1000),
        Decimal("1"),
        "F004-media-validation-v1",
        hashlib.sha256(b"F004-media-validation-v1").hexdigest(),
        ("media",),
    )
    run_ids = []
    expected: list[dict[str, object]] = []
    try:
        for index, source in enumerate(sources):
            run_id = f"media-{index:03d}"
            run_ids.append(run_id)
            bundle = await processor.preprocess(
                source,
                project / "runs" / run_id / "media",
                SamplingParameters(),
                CancellationContext(run_id, 180),
            )
            await store.create_run(run_id, bundle.asset, config)
            await store.begin_stage(run_id, "media", bundle.asset.sha256)
            await store.persist_media_bundle(run_id, bundle)
            await store.complete_run(run_id)
            # Equality includes every original PTS/time base and audio mapping piece.
            if await store.load_media_bundle(run_id) != bundle:
                raise AssertionError("Media bundle did not round-trip exactly")
        expected = await read_project(project, run_ids)
    finally:
        await store.close()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-B",
        "-W",
        "error",
        str(Path(__file__).resolve()),
        "--read-project",
        str(project),
        "--runs",
        *run_ids,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    if process.returncode != 0 or stderr or json.loads(stdout) != expected:
        raise AssertionError("Second-process media read failed")
    report = project / "validation.json"
    report.write_text(
        json.dumps(
            {
                "feature": "F004",
                "status": "completed",
                "scope": "media-only storage validation",
                "secondProcess": True,
                "exactBundleRoundTrip": True,
                "cases": expected,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Local F004 storage validation")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--input", type=Path)
    selection.add_argument("--all-local", action="store_true")
    selection.add_argument("--read-project", type=Path)
    parser.add_argument("--runs", nargs="+", default=[])
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    try:
        if args.read_project:
            print(json.dumps(asyncio.run(read_project(args.read_project, args.runs))))
        else:
            sources = (
                sorted((repository / "GameVideos").rglob("*.mp4"))
                if args.all_local
                else [args.input.resolve()]
            )
            if not sources:
                return 2
            report = asyncio.run(validate(sources, repository))
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
