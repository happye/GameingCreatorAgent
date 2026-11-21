"""Saved timelines and bounded, locally generated transparent layer bundles."""

from __future__ import annotations

import asyncio
import json
import shutil
import wave
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from zipfile import ZIP_STORED, ZipFile

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.timeline_export import (
    ExportLayer,
    ExportMusic,
    ExportNarration,
    MusicTimelineError,
    captions_from_cues,
    to_fcpxml,
    to_otio,
    to_xmeml,
)
from gamingcreator.domain.creation_subtitles import serialize_srt
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.music_library import MusicLibrary
from gamingcreator.infrastructure.overlay_assets import OverlayAssetLibrary, resolve_overlay_assets
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock
from gamingcreator.ui.creation_jobs import fail
from gamingcreator.ui.revision_jobs import Chain, load_chain, revision_subtitles

if TYPE_CHECKING:
    from gamingcreator.ui.creation_jobs import CreationJobs


_FILES = {
    "fcpxml": (".fcpxml", "application/xml"),
    "otio": (".otio", "application/json"),
    "xmeml": ("-premiere.xml", "application/xml"),
    "srt": (".srt", "application/x-subrip"),
}


def _size(value: str) -> tuple[int, int]:
    width, _, height = value.partition("x")
    if not (width.isdecimal() and height.isdecimal()) or not all(
        16 <= int(v) <= 3840 and int(v) % 2 == 0 for v in (width, height)
    ):
        raise fail("creation.input", "时间线尺寸须为 16–3840 之间的偶数，如 1280x720。")
    return int(width), int(height)


def _saved_chain(jobs: CreationJobs, job_id: str, plan_id: str) -> Chain:
    try:
        return load_chain(jobs, job_id, plan_id, read_only=True)
    except (EOFError, wave.Error) as error:
        raise ValueError("旁白 WAV 已损坏，请检查已保存的素材。") from error


def _saved_music(jobs: CreationJobs, chain: Chain, include_music: bool) -> ExportMusic | None:
    selection = chain.audio_mix.bgm
    if selection is None or not include_music:
        return None
    library = MusicLibrary(jobs.repository)
    track = library.resolve(selection.track_id, selection.track_receipt_sha256)
    try:
        length, sample_rate, channels, depth = asyncio.run(library.probe_audio_stream(track))
    except ValueError as error:
        raise fail("creation.input", str(error)) from error
    return ExportMusic(str(track.path), track.title, length, sample_rate, channels, depth)


def _documents(
    jobs: CreationJobs,
    chain: Chain,
    name: str,
    formats: tuple[str, ...],
    canvas: tuple[int, int],
    include_music: bool,
    layers: Sequence[ExportLayer] = (),
) -> dict[str, bytes]:
    try:
        cues = revision_subtitles(chain, "sidecar")
    except (KeyError, ValueError) as error:
        raise fail("creation.input", "无法读取当前已保存版本的字幕。") from error
    documents: dict[str, bytes] = {}
    if "srt" in formats and (srt := serialize_srt(cues)):
        documents["srt"] = srt.encode("utf-8")
    if formats == ("srt",):
        if not documents:
            raise fail("creation.input", "当前已保存版本没有可导出的字幕。")
        return documents
    captions = captions_from_cues(cues, chain.plan.fps)
    narration = None
    if chain.narration is not None and (asset := chain.narration_asset) is not None:
        narration = ExportNarration(
            str(asset.wav_path),
            chain.narration.start_frame,
            asset.sample_rate,
            asset.channels,
            asset.sample_width,
            asset.sample_count,
        )
    music = _saved_music(jobs, chain, include_music)
    try:
        if "fcpxml" in formats:
            documents["fcpxml"] = to_fcpxml(
                chain.edl,
                name,
                *canvas,
                captions=captions,
                include_audio_track=True,
                narration=narration,
                music=music,
                layers=layers,
            ).encode("utf-8")
        if "otio" in formats:
            documents["otio"] = to_otio(
                chain.edl,
                name,
                captions=captions,
                include_audio_track=True,
                narration=narration,
                music=music,
                layers=layers,
            ).encode("utf-8")
        if "xmeml" in formats:
            documents["xmeml"] = to_xmeml(
                chain.edl,
                name,
                captions=captions,
                include_audio_track=True,
                narration=narration,
                music=music,
                layers=layers,
            ).encode("utf-8")
    except MusicTimelineError as error:
        raise fail("creation.input", str(error)) from error
    return documents


def export_timeline(
    jobs: CreationJobs, job_id: str, plan_id: str, fmt: str, size: str, include_music: bool
) -> tuple[bytes, str, str]:
    if fmt not in _FILES:
        raise fail("creation.input", "时间线格式只支持 fcpxml、otio、xmeml 或 srt。")
    canvas = _size(size)
    suffix, media_type = _FILES[fmt]
    name = f"gamingcreator-{job_id[:8]}"
    chain = _saved_chain(jobs, job_id, plan_id)
    return (
        _documents(jobs, chain, name, (fmt,), canvas, include_music)[fmt],
        name + suffix,
        media_type,
    )


async def _render_layers(
    jobs: CreationJobs, chain: Chain, directory: Path, canvas: tuple[int, int]
) -> tuple[Path, ...]:
    from gamingcreator.infrastructure.overlay_handoff import render_overlay_layers

    deadline = 180
    async with asyncio.timeout(deadline):
        return await render_overlay_layers(
            jobs.repository / ".tools/ffmpeg/bin",
            directory,
            chain.overlays,
            chain.overlay_assets,
            chain.plan.frames,
            chain.plan.fps,
            *canvas,
            CancellationContext("timeline-overlay-bundle", deadline),
        )


def _archive_layers(
    jobs: CreationJobs,
    chain: Chain,
    job_id: str,
    directory: Path,
    canvas: tuple[int, int],
    include_music: bool,
) -> Path:
    from gamingcreator.infrastructure.overlay_handoff import MAX_LAYER_BYTES

    try:
        paths = asyncio.run(_render_layers(jobs, chain, directory, canvas))
    except TimeoutError:
        raise AppError(
            "media.timeout", "图层交接处理超时，请缩短图层或降低输出尺寸。", ExitCode.ENVIRONMENT
        ) from None
    except ValueError as error:
        raise fail("creation.input", str(error)) from error
    verified = resolve_overlay_assets(OverlayAssetLibrary(jobs.repository), chain.overlays)
    if verified != chain.overlay_assets:
        raise fail("creation.artifact_invalid", "图层素材在导出期间变化。", True)
    layers = tuple(
        ExportLayer(path.name, item.start_frame, item.end_frame, *canvas)
        for path, item in zip(paths, chain.overlays.items, strict=True)
    )
    documents = _documents(jobs, chain, "timeline", tuple(_FILES), canvas, include_music, layers)
    media_bytes = sum(path.stat().st_size for path in paths)
    document_bytes = sum(len(body) for body in documents.values())
    if media_bytes > MAX_LAYER_BYTES or document_bytes > 16 * 1024**2:
        raise fail("creation.input", "图层包超出容量上限，请缩短或降低输出尺寸。")
    if shutil.disk_usage(directory).free < 256 * 1024**2 + media_bytes + document_bytes:
        raise fail("creation.input", "本机剩余空间不足以写入图层包。")
    manifest = {
        "schemaVersion": "gamingcreator-timeline-layers-v1",
        "jobId": job_id,
        "planId": chain.plan_id,
        "revisionReceiptSha256": chain.digest,
        "fps": chain.plan.fps,
        "frames": chain.plan.frames,
        "width": canvas[0],
        "height": canvas[1],
        "layers": [
            {**item.to_json(), "trackOrder": index, "file": layer.url, "sha256": hash_file(path)}
            for index, (item, layer, path) in enumerate(
                zip(chain.overlays.items, layers, paths, strict=True), 1
            )
        ],
    }
    archive_path = directory / "timeline.zip"
    with ZipFile(archive_path, "x", compression=ZIP_STORED) as archive:
        for fmt, body in documents.items():
            archive.writestr("subtitles.srt" if fmt == "srt" else "timeline" + _FILES[fmt][0], body)
        for layer, path in zip(layers, paths, strict=True):
            archive.write(path, layer.url)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return archive_path


@contextmanager
def timeline_bundle(
    jobs: CreationJobs,
    project_id: str,
    job_id: str,
    plan_id: str,
    receipt: str,
    size: str,
    include_music: bool,
) -> Iterator[tuple[Path, str]]:
    canvas = _size(size)
    chain = _saved_chain(jobs, job_id, plan_id)
    if chain.project_id != project_id or chain.digest != receipt:
        raise fail("creation.artifact_invalid", "保存版本已变化，请重开后导出。", True)
    if not chain.overlays.items:
        raise fail("creation.input", "当前版本没有已保存的图层。")
    scratch = jobs.safe(jobs.root / "timeline-bundles")
    scratch.mkdir(exist_ok=True)
    jobs.safe(scratch / ".analysis-writer.lock")
    lock = ProjectWriterLock(scratch)
    lock.acquire()
    try:
        with TemporaryDirectory(prefix="layers-", dir=scratch) as temporary:
            archive = _archive_layers(jobs, chain, job_id, Path(temporary), canvas, include_music)
            if _saved_chain(jobs, job_id, plan_id).digest != chain.digest:
                raise fail("creation.artifact_invalid", "保存版本在导出期间变化。", True)
            yield archive, f"gamingcreator-{job_id[:8]}-layers.zip"
    finally:
        lock.close()
