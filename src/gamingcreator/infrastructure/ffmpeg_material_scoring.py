"""Measure contrast in verified, saved analysis frames without decoding the source footage."""

import hashlib
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from threading import BoundedSemaphore
from time import monotonic

from gamingcreator.application.creative_planner import CreationClip
from gamingcreator.application.material_scoring import VisualSample
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.models import EvidenceReference
from gamingcreator.domain.time import SourceInstant
from gamingcreator.infrastructure.local_files import read_bounded
from gamingcreator.infrastructure.media_process import run_media_process

_WIDTH, _HEIGHT = 160, 90
_FRAME_BYTES = _WIDTH * _HEIGHT
_MAX_FRAMES = 256
_MAX_JPEG_BYTES = 2 * 1024 * 1024
_MAX_BATCH_BYTES = 16 * 1024 * 1024
_SCAN_SECONDS = 12
_SCAN_SLOTS = BoundedSemaphore(2)


def _contrast(pixels: bytes) -> int:
    histogram = Counter(pixels)
    low_rank, high_rank = (len(pixels) - 1) // 10, (len(pixels) - 1) * 9 // 10
    low = None
    count = 0
    for value in sorted(histogram):
        count += histogram[value]
        if low is None and count > low_rank:
            low = value
        if low is not None and count > high_rank:
            return value - low
    return 0


def _frames_for_clips(
    timelines: Sequence[StoredTimeline], clips: Sequence[CreationClip]
) -> dict[str, list[EvidenceReference]]:
    by_run = {
        timeline.run.run_id: {frame.evidence_id: frame for frame in timeline.evidence}
        for timeline in timelines
    }
    wanted: dict[tuple[str, str], EvidenceReference] = {}
    for clip in clips:
        event = clip.event
        for identity in event.evidence_ids:
            frame = by_run[event.run_id][identity]
            if (
                frame.kind == "image"
                and frame.media_id == clip.asset.media_id
                and isinstance(frame.source_time, SourceInstant)
                and frame.source_time.duration_us == clip.asset.duration_us
                and clip.framing.start_us <= frame.source_time.time_us < clip.framing.end_us
            ):
                wanted[(event.run_id, identity)] = frame
    ordered = list(wanted.items())
    if len(ordered) > _MAX_FRAMES:
        ordered = [ordered[index * len(ordered) // _MAX_FRAMES] for index in range(_MAX_FRAMES)]
    batches: dict[str, list[EvidenceReference]] = {}
    for (run_id, _), frame in ordered:
        batches.setdefault(run_id, []).append(frame)
    return batches


async def _measure_batch(
    project: Path, tool: Path, frames: list[EvidenceReference], deadline: float
) -> dict[str, VisualSample]:
    images = bytearray()
    verified: list[EvidenceReference] = []
    for frame in frames:
        if monotonic() >= deadline:
            return {}
        try:
            path = frame.artifact_path.resolve(strict=True)
            if not path.is_relative_to(project) or path.suffix.lower() not in (".jpg", ".jpeg"):
                continue
            if not path.is_file():
                continue
            content = read_bounded(path, min(_MAX_JPEG_BYTES, _MAX_BATCH_BYTES - len(images)))
        except (OSError, ValueError):
            continue
        if hashlib.sha256(content).hexdigest() != frame.sha256:
            continue
        images.extend(content)
        verified.append(frame)
        if len(images) == _MAX_BATCH_BYTES:
            break
    remaining = deadline - monotonic()
    if not verified or remaining <= 0:
        return {}
    output = await run_media_process(
        [
            str(tool),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-xerror",
            "-protocol_whitelist",
            "pipe",
            "-f",
            "image2pipe",
            "-c:v",
            "mjpeg",
            "-err_detect",
            "explode",
            "-i",
            "pipe:0",
            "-an",
            "-vf",
            f"scale={_WIDTH}:{_HEIGHT}:flags=area,format=gray",
            "-fps_mode",
            "passthrough",
            "-threads:v",
            "1",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        CancellationContext("material-scoring", remaining),
        max_stdout_bytes=len(verified) * _FRAME_BYTES,
        input_data=images,
    )
    if len(output.stdout) != len(verified) * _FRAME_BYTES:
        return {}
    samples = {}
    for index, frame in enumerate(verified):
        if isinstance(frame.source_time, SourceInstant):
            start = index * _FRAME_BYTES
            samples[frame.evidence_id] = VisualSample(
                frame.source_time.time_us,
                frame.sha256,
                _contrast(output.stdout[start : start + _FRAME_BYTES]),
            )
    return samples


async def measure_visual_samples(
    project: Path,
    repository: Path,
    timelines: Sequence[StoredTimeline],
    clips: Sequence[CreationClip],
) -> dict[tuple[str, str], VisualSample]:
    repository, project = repository.resolve(), project.resolve()
    tool = repository / ".tools/ffmpeg/bin/ffmpeg.exe"
    if not tool.is_file() or not _SCAN_SLOTS.acquire(blocking=False):
        return {}
    samples: dict[tuple[str, str], VisualSample] = {}
    deadline = monotonic() + _SCAN_SECONDS
    try:
        for run_id, frames in _frames_for_clips(timelines, clips).items():
            if monotonic() >= deadline:
                break
            try:
                measured = await _measure_batch(project, tool, frames, deadline)
            except (AppError, OSError):
                continue
            samples.update({(run_id, key): value for key, value in measured.items()})
    finally:
        _SCAN_SLOTS.release()
    return samples
