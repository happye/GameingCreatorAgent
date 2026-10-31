"""Local narration jobs and immutable output-clock attachments."""

import asyncio
from pathlib import Path
from typing import Any

from gamingcreator.application.narration import NarrationArtifact, NarrationRequest
from gamingcreator.domain.creation_narration import NarrationSelection, validate_narration_fit
from gamingcreator.infrastructure.sapi_narration import (
    list_local_voices,
    read_narration_artifact,
    synthesize_local_narration,
)
from gamingcreator.ui.media import MediaResource


def voices() -> dict[str, Any]:
    return {
        "voices": [
            {"voiceId": v.voice_id, "description": v.description, "language": v.language}
            for v in asyncio.run(list_local_voices())
        ],
        "licenseStatus": "unknown",
    }


def public(job_id: str, artifact: NarrationArtifact) -> dict[str, Any]:
    prefix = f"/api/creation/jobs/{job_id}/narration-files/"
    return {
        "assetJobId": job_id,
        "receiptSha256": artifact.receipt_sha256,
        "voice": {
            "voiceId": artifact.voice.voice_id,
            "description": artifact.voice.description,
            "language": artifact.voice.language,
        },
        "sampleRate": artifact.sample_rate,
        "sampleCount": artifact.sample_count,
        "durationSeconds": artifact.duration_seconds,
        "text": artifact.text_path.read_text(encoding="utf-8"),
        "audioUrl": prefix + "narration.wav",
        "textUrl": prefix + "narration.txt",
        "licenseStatus": "unknown",
    }


def verify_asset(jobs: Any, directory: Path, state: dict[str, Any], stored: dict[str, Any]) -> None:
    request = stored["request"]
    artifact = read_narration_artifact(jobs.safe(directory / "result"))
    receipt = jobs.read(artifact.receipt_path)
    if (
        state["parentJobId"] is not None
        or receipt["jobId"] != directory.name
        or request["projectId"] != state["projectId"]
        or receipt["projectId"] != state["projectId"]
        or receipt["requestId"] != request["requestId"]
        or artifact.voice.voice_id != request["voiceId"]
        or artifact.text_path.read_bytes().decode("utf-8") != request["text"]
    ):
        raise ValueError("Narration result differs from its saved request.")
    state["narrationAsset"] = public(directory.name, artifact)


def asset(jobs: Any, selection: NarrationSelection, project_id: str) -> NarrationArtifact:
    state = jobs.get(selection.asset_job_id)
    if (
        state["kind"] != "narration"
        or state["status"] != "completed"
        or state["projectId"] != project_id
    ):
        raise ValueError("Narration must be a completed asset of this project.")
    return read_narration_artifact(
        jobs.safe(jobs.directory(selection.asset_job_id) / "result"), selection.receipt_sha256
    )


def resolve(
    jobs: Any,
    request: dict[str, Any],
    inherited: NarrationSelection | None,
    project_id: str,
    frames: int,
    fps: int,
) -> NarrationSelection | None:
    selection = inherited
    if "narration" in request:
        selection = (
            None
            if request["narration"] is None
            else NarrationSelection.from_json(request["narration"])
        )
    if selection is not None:
        source = asset(jobs, selection, project_id)
        try:
            validate_narration_fit(selection, source.sample_count, source.sample_rate, frames, fps)
        except ValueError as error:
            raise ValueError(
                f"旁白长 {source.duration_seconds:.3f} 秒，起点后只剩 "
                f"{max(0, frames - selection.start_frame) / fps:.3f} 秒；"
                "请改短文字、调整起点或移除旁白，不会自动截断。"
            ) from error
    return selection


async def generate(jobs: Any, directory: Path, request: dict[str, Any]) -> None:
    with jobs.narration_lock:
        context, _ = jobs.narration_contexts[directory.name]
        jobs.narration_contexts[directory.name] = (context, asyncio.get_running_loop())
    await synthesize_local_narration(
        NarrationRequest(
            request["requestId"], request["projectId"], request["text"], request["voiceId"]
        ),
        jobs.safe(directory / "result"),
        context,
    )


def cancel(jobs: Any, job_id: str) -> dict[str, Any]:
    directory = jobs.directory(job_id)
    state = jobs.read(directory / "status.json")
    if state["kind"] != "narration":
        raise ValueError("Only local narration generation can be cancelled here.")
    with jobs.narration_lock:
        running = jobs.narration_contexts.get(job_id)
        if running is not None:
            context, loop = running
            jobs.narration_cancel_requests.add(job_id)
            if loop is None:
                context.cancelled.set()
            else:
                try:
                    loop.call_soon_threadsafe(context.cancelled.set)
                except RuntimeError:
                    if not loop.is_closed():
                        raise
            return {
                "jobId": job_id,
                "kind": "narration",
                "status": state["status"],
                "cancelRequested": True,
            }
    state = jobs.get(job_id)
    if state["status"] in ("pending", "running"):
        raise ValueError("This narration is owned by another workspace process.")
    return {
        "jobId": job_id,
        "kind": "narration",
        "status": state["status"],
        "cancelRequested": False,
    }


def resource(jobs: Any, job_id: str, name: str) -> MediaResource:
    types = {"narration.wav": "audio/wav", "narration.txt": "text/plain; charset=utf-8"}
    if name not in types:
        raise ValueError("Unknown narration file.")
    state = jobs.get(job_id)
    if state["kind"] != "narration" or state["status"] != "completed":
        raise ValueError("Narration is not completed.")
    selected = state["narrationAsset"]
    artifact = asset(
        jobs,
        NarrationSelection.from_json(
            {
                "assetJobId": job_id,
                "receiptSha256": selected["receiptSha256"],
                "startFrame": 0,
                "gainDb": 0,
                "ducking": "off",
            }
        ),
        state["projectId"],
    )
    return MediaResource(
        artifact.wav_path if name == "narration.wav" else artifact.text_path,
        artifact.wav_sha256 if name == "narration.wav" else artifact.text_sha256,
        types[name],
    )
