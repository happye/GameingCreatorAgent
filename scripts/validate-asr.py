"""Explicit local ASR experiment. No paid API; output is not a retrieval benchmark."""

import argparse
import asyncio
import hashlib
import json
import os
import uuid
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path

from gamingcreator.application.asr import LocalAsrSettings, ModelFile
from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import (
    AsrRequest,
    CancellationContext,
    InvocationMetadata,
    ProviderStatus,
    ProviderUsage,
)
from gamingcreator.application.storage import InvocationStatus, RunConfiguration, RunStatus
from gamingcreator.domain.models import EvidenceReference
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.local_asr import LocalAsrProvider
from gamingcreator.infrastructure.media_process import run_media_process
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def write_report(report: Path, cases: list[dict[str, object]], *, completed: bool) -> None:
    expected = {"synthetic-silence": "no_speech", "synthetic-no-audio": "no_audio"}
    passed = all(
        case["status"] == expected[case["label"]]
        if case["label"] in expected
        else case["status"] in ("completed", "no_speech")
        for case in cases
    )
    payload = {
        "feature": "F003-ASR",
        "scope": "runtime/storage validation, ungraded transcripts",
        "state": "completed" if completed else "running",
        "validationPassed": passed if completed else None,
        "packageVersions": {
            package: version(package)
            for package in ("faster-whisper", "ctranslate2", "av", "onnxruntime")
        },
        "cases": cases,
    }
    temporary = report.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        output.write(json.dumps(payload, ensure_ascii=False, indent=2))
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(report)


def settings(repository: Path) -> LocalAsrSettings:
    pin = json.loads((repository / "docs/references/asr-models.json").read_text())
    native = json.loads((repository / "docs/references/asr-native-toolchain.json").read_text())
    native_directory = repository / ".tools/native/msvc" / native["version"]
    return LocalAsrSettings(
        repository / ".cache/models/faster-whisper/tiny" / pin["revision"],
        pin["model"],
        pin["revision"],
        tuple(ModelFile(**file) for file in pin["files"]),
        native_directory,
        native_library_files=tuple(
            ModelFile(name, (native_directory / name).stat().st_size, sha)
            for name, sha in native["files"].items()
        ),
    )


async def synthetic(repository: Path, directory: Path, *, audio: bool) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / ("silence.mp4" if audio else "no-audio.mp4")
    arguments = [
        str(repository / ".tools/ffmpeg/bin/ffmpeg.exe"),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=size=64x64:rate=10:duration=2",
    ]
    if audio:
        arguments += ["-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=2", "-c:a", "aac"]
    arguments += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)]
    await run_media_process(arguments, CancellationContext("generate", 30))
    return output


async def validate(repository: Path, sources: list[Path], *, include_fixtures: bool) -> Path:
    project = repository / "artifacts/asr-F003" / uuid.uuid4().hex
    project.mkdir(parents=True)
    report = project / "validation.json"
    cases: list[dict[str, object]] = []
    write_report(report, cases, completed=False)
    labeled_sources = [(source.name, source, "auto") for source in sources]
    if include_fixtures:
        for label, has_audio in (("synthetic-silence", True), ("synthetic-no-audio", False)):
            labeled_sources.append(
                (label, await synthetic(repository, project / "fixtures", audio=has_audio), "zh")
            )
    store = await SqliteTimelineStore.open(project)
    processor = FfmpegMediaProcessor(repository)
    provider_settings = settings(repository)
    provider = LocalAsrProvider(repository, provider_settings)
    configuration = RunConfiguration(
        AnalysisConfig("none", "local-asr-validation", 1, 1000),
        Decimal("1"),
        "F003-ASR-validation-v1",
        hashlib.sha256(b"F003-ASR-validation-v1").hexdigest(),
        ("media", "asr"),
    )
    try:
        for index, (label, source, language) in enumerate(labeled_sources):
            run_id = f"asr-{index:03d}"
            bundle = await processor.preprocess(
                source,
                project / "runs" / run_id / "media",
                SamplingParameters(),
                CancellationContext(run_id, 180),
            )
            await store.create_run(run_id, bundle.asset, configuration)
            await store.begin_stage(run_id, "media", bundle.asset.sha256)
            await store.persist_media_bundle(run_id, bundle)
            audio = bundle.audio
            reference = (
                None
                if audio is None
                else EvidenceReference(
                    audio.evidence_id,
                    bundle.asset.media_id,
                    "audio",
                    audio.map_interval(0, audio.sample_count, bundle.asset).source_range,
                    audio.path,
                    audio.sha256,
                    bundle.transform_version,
                )
            )
            request = AsrRequest(
                run_id,
                reference,
                "transcript-v1",
                language,
                media_asset=bundle.asset,
                audio_clock=audio,
            )
            await store.begin_stage(run_id, "asr", bundle.asset.sha256)
            initial = InvocationMetadata(
                "faster-whisper-local",
                provider_settings.model_name,
                None,
                provider_settings.model_revision,
                "asr-hotwords-v1",
                request.schema_version,
                1,
                ProviderUsage(),
            )
            await store.begin_invocation(run_id, run_id, "asr", "transcription", initial)
            result = await provider.transcribe(request, CancellationContext(run_id, 180))
            await store.finish_invocation(
                run_id,
                InvocationStatus(result.status.value),
                result.metadata,
                None if result.error is None else result.error.code,
            )
            if result.output is not None:
                payload = [
                    {
                        "startUs": segment.source_range.start_us,
                        "endUs": segment.source_range.end_us,
                        "text": segment.text,
                        "uncertainty": segment.uncertainty,
                    }
                    for segment in result.output
                ]
                output_hash = hashlib.sha256(
                    json.dumps(payload, sort_keys=True).encode()
                ).hexdigest()
                await store.persist_timeline(run_id, "asr", (), result.output, output_hash)
                await store.complete_run(run_id)
                if (await store.load_completed_timeline(run_id)).transcripts != result.output:
                    raise AssertionError("ASR transcripts did not round-trip")
            else:
                payload = []
                await store.stop_run(
                    run_id,
                    RunStatus.CANCELLED
                    if result.status == ProviderStatus.CANCELLED
                    else RunStatus.FAILED,
                    "asr.validation_failed",
                )
            summary: dict[str, object] = {
                "label": label,
                "runId": run_id,
                "sourceSha256": bundle.asset.sha256,
                "durationUs": bundle.asset.duration_us,
                "status": result.status.value,
                "error": None if result.error is None else result.error.code,
                "segments": payload,
                "elapsedMs": result.metadata.elapsed_ms,
                "executionDetails": json.loads(result.metadata.execution_details or "{}"),
                "billingScope": "zero network API charge; hardware cost not measured",
            }
            cases.append(summary)
            write_report(report, cases, completed=False)
            print(
                json.dumps(
                    {
                        "label": label,
                        "status": result.status.value,
                        "segments": len(payload),
                        "elapsedMs": result.metadata.elapsed_ms,
                        "error": summary["error"],
                    },
                    ensure_ascii=True,
                ),
                flush=True,
            )
    finally:
        await store.close()
    write_report(report, cases, completed=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all-local", action="store_true")
    selection.add_argument("--input", type=Path)
    selection.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    sources = (
        sorted((repository / "GameVideos").rglob("*.mp4"))
        if args.all_local
        else ([args.input.resolve()] if args.input else [])
    )
    report = asyncio.run(validate(repository, sources, include_fixtures=True))
    print(json.dumps({"report": str(report)}, ensure_ascii=False))
    return 0 if json.loads(report.read_text(encoding="utf-8"))["validationPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
