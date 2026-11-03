"""Local narration jobs and immutable output-clock attachments."""

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gamingcreator.application.narration import NarrationArtifact, NarrationRequest
from gamingcreator.domain.creation_narration import NarrationSelection, validate_narration_fit
from gamingcreator.infrastructure import cosyvoice_tts
from gamingcreator.infrastructure.sapi_narration import (
    list_local_voices,
    read_narration_artifact,
    synthesize_cloud_narration,
    synthesize_local_narration,
)
from gamingcreator.ui.media import MediaResource

CLOUD = "cosyvoice:"
DEFAULT_CLOUD_VOICE = CLOUD + "longanyang"  # chosen by the user after the audition, 2026-11-03
# Hard monthly ceiling for paid narration; every call is also confirmed with its cost first.
MONTHLY_CAP_YUAN = 5.0


def voices(repository: Path) -> dict[str, Any]:
    local = [
        {"voiceId": v.voice_id, "description": v.description, "language": v.language, "paid": False}
        for v in asyncio.run(list_local_voices())
    ]
    configured = bool(os.environ.get("DASHSCOPE_API_KEY", "").strip())
    cloud = [
        {
            "voiceId": CLOUD + name,
            "description": f"{label}（云端，付费）",
            "language": "zh-CN",
            "paid": True,
            "available": configured,
            "yuanPer10kCharacters": cosyvoice_tts.YUAN_PER_10K_CHARACTERS,
        }
        for name, label in cosyvoice_tts.VOICES.items()
    ]
    return {
        "voices": local + cloud,
        "defaultVoiceId": DEFAULT_CLOUD_VOICE if configured else None,
        "monthlyCapYuan": MONTHLY_CAP_YUAN,
        "spentThisMonthYuan": round(_spent(_rows(repository)), 4),
        "licenseStatus": "unknown",
    }


def estimate_yuan(text: str) -> float:
    return cosyvoice_tts.estimated_characters(text) * cosyvoice_tts.YUAN_PER_10K_CHARACTERS / 10000


def _ledger(repository: Path) -> Path:
    # Billing records live with the user's artifacts, never in the rebuildable cache.
    return Path(repository) / "artifacts/billing/narration-tts.jsonl"


def _rows(repository: Path) -> list[dict[str, Any]]:
    path = _ledger(repository)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _spent(rows: list[dict[str, Any]]) -> float:
    month = datetime.now(UTC).strftime("%Y-%m")
    return sum(
        float(r["estimatedYuan"])
        for r in rows
        if r["event"] == "planned" and r["at"].startswith(month)
    )


def _record(repository: Path, row: dict[str, Any]) -> None:
    path = _ledger(repository)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"at": datetime.now(UTC).isoformat(), **row}, ensure_ascii=False)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line + "\n")


def paid_gate(jobs: Any, request: dict[str, Any]) -> str | None:
    """Before registering a narration job: refuse unconfirmed or over-cap paid synthesis.

    Returns the id of an earlier completed job with the same project, voice and text, so the
    same narration is never paid for twice.
    """
    confirmed = request.get("costConfirmationYuan")
    if not request["voiceId"].startswith(CLOUD):
        if "costConfirmationYuan" in request:
            raise ValueError("Local voices are free; no cost confirmation is expected.")
        return None
    if not os.environ.get("DASHSCOPE_API_KEY", "").strip():
        raise ValueError(
            "云端语音未配置：在启动工作台的终端里设置 DASHSCOPE_API_KEY 后重启工作台。"
        )
    cost = estimate_yuan(request["text"])
    if not isinstance(confirmed, int | float) or float(confirmed) + 1e-9 < round(cost, 4):
        raise ValueError(f"这次合成预计 ¥{cost:.4f}，请先确认费用。")
    rows = _rows(jobs.repository)
    key = (
        request["projectId"],
        request["voiceId"],
        hashlib.sha256(request["text"].encode("utf-8")).hexdigest(),
    )
    for row in reversed(rows):
        if (
            row["event"] == "completed"
            and (row["projectId"], row["voiceId"], row["textSha256"]) == key
        ):
            try:
                if jobs.get(row["jobId"])["status"] == "completed":
                    return str(row["jobId"])
            except (OSError, ValueError, KeyError):
                continue
    spent = _spent(rows)
    if spent + cost > MONTHLY_CAP_YUAN:
        raise ValueError(
            f"本月云端旁白已用约 ¥{spent:.2f}，再合成会超过 ¥{MONTHLY_CAP_YUAN:.0f} 上限；"
            "需要你重新授权。"
        )
    return None


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
    narration = NarrationRequest(
        request["requestId"], request["projectId"], request["text"], request["voiceId"]
    )
    if not narration.voice_id.startswith(CLOUD):
        await synthesize_local_narration(narration, jobs.safe(directory / "result"), context)
        return
    row = {
        "jobId": directory.name,
        "projectId": narration.project_id,
        "voiceId": narration.voice_id,
        "model": cosyvoice_tts.MODEL,
        "textSha256": hashlib.sha256(narration.text.encode("utf-8")).hexdigest(),
    }
    # Planned before sending, so a crash mid-call still counts against the month.
    _record(
        jobs.repository, {"event": "planned", **row, "estimatedYuan": estimate_yuan(narration.text)}
    )
    try:
        _, billed, provider_id = await synthesize_cloud_narration(
            narration, jobs.safe(directory / "result"), context
        )
    except BaseException as error:
        _record(jobs.repository, {"event": "failed", **row, "error": str(error)[:300]})
        raise
    _record(
        jobs.repository,
        {"event": "completed", **row, "billedCharacters": billed, "providerRequestId": provider_id},
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
            # Persist first: a crash after this point must never promote the job to completed.
            jobs.save(directory / "cancel-requested.json", {"jobId": job_id})
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
