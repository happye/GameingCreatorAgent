"""Saved timelines and bounded, locally generated transparent layer bundles."""

from __future__ import annotations

import asyncio
import json
import shutil
import wave
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from zipfile import ZIP_STORED, ZipFile

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.timeline_export import (
    ExportLayer,
    ExportMusic,
    ExportNarration,
    ExportReferenceMix,
    MusicTimelineError,
    captions_from_cues,
    to_fcpxml,
    to_otio,
    to_xmeml,
)
from gamingcreator.domain.creation_subtitles import serialize_srt
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.music_library import MusicLibrary, UnsupportedTimelineMusic
from gamingcreator.infrastructure.overlay_assets import OverlayAssetLibrary, resolve_overlay_assets
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock
from gamingcreator.ui.creation_jobs import fail
from gamingcreator.ui.publication_jobs import render_parent
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
    except UnsupportedTimelineMusic as error:
        raise MusicTimelineError(str(error)) from error
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
    reference_mix: ExportReferenceMix | None = None,
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
    music = _saved_music(jobs, chain, include_music and reference_mix is None)
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
            reference_mix=reference_mix,
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
            reference_mix=reference_mix,
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
            reference_mix=reference_mix,
            canvas=canvas,
        ).encode("utf-8")
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
    try:
        body = _documents(jobs, chain, name, (fmt,), canvas, include_music)[fmt]
    except MusicTimelineError as error:
        raise fail("creation.input", str(error)) from error
    return body, name + suffix, media_type


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


@dataclass(frozen=True, slots=True)
class ReferenceRender:
    job_id: str
    receipt_sha256: str


def _extract_mix(
    jobs: CreationJobs, chain: Chain, job_id: str, requested: ReferenceRender, output: Path
) -> tuple[ExportReferenceMix, dict[str, object]]:
    from gamingcreator.infrastructure.mix_handoff import extract_render_mix

    directory = jobs.directory(requested.job_id)
    stored = jobs.read(directory / "request.json")
    request = stored["request"]
    state, receipt, digest = render_parent(jobs, requested.job_id)
    belongs = request.get("revisionJobId") == job_id or (
        request.get("planJobId") == job_id and request.get("planId") == chain.plan_id
    )
    if (
        not belongs
        or state.get("parentJobId") != job_id
        or state["projectId"] != chain.project_id
        or stored["parentReceiptSha256"] != chain.digest
        or digest != requested.receipt_sha256
        or receipt["frames"] != chain.plan.frames
        or receipt["fpsNumerator"] != chain.plan.fps
        or receipt["fpsDenominator"] != 1
    ):
        raise fail(
            "creation.artifact_invalid", "成片与当前已保存版本或时钟不一致，请重开对应成片。", True
        )
    video = jobs.safe(directory / "result/video.mp4")
    video_sha = receipt["files"]["video.mp4"]
    try:
        samples = asyncio.run(
            extract_render_mix(
                jobs.repository / ".tools/ffmpeg/bin",
                video,
                output,
                chain.plan.frames,
                chain.plan.fps,
                CancellationContext("timeline-reference-mix", 90),
            )
        )
    except ValueError as error:
        raise fail("creation.input", str(error)) from error
    receipt_path = jobs.safe(directory / "result/receipt.json")
    if hash_file(video) != video_sha or hash_file(receipt_path) != digest:
        raise fail("creation.artifact_invalid", "成片或回执在导出混音时发生变化。", True)
    mix = ExportReferenceMix(samples)
    return mix, {
        "renderJobId": requested.job_id,
        "renderReceiptSha256": digest,
        "renderVideoSha256": video_sha,
        "file": mix.path,
        "sha256": hash_file(output),
        "sampleCount": samples,
        "sampleRate": mix.sample_rate,
        "channels": mix.channels,
        "depth": mix.depth,
        "audioMix": chain.audio_mix.to_json(),
        "mixPolicy": receipt.get("mixPolicy"),
        "narration": chain.narration.to_json() if chain.narration else None,
    }


def _archive_layers(
    jobs: CreationJobs,
    chain: Chain,
    job_id: str,
    directory: Path,
    canvas: tuple[int, int],
    include_music: bool,
    reference: ReferenceRender | None = None,
) -> Path:
    from gamingcreator.infrastructure.overlay_handoff import MAX_LAYER_BYTES

    mix_asset = directory / ExportReferenceMix.path
    mix, mix_record = (
        _extract_mix(jobs, chain, job_id, reference, mix_asset) if reference else (None, None)
    )
    paths = _bundle_layer_media(jobs, chain, directory, canvas)
    verified = resolve_overlay_assets(OverlayAssetLibrary(jobs.repository), chain.overlays)
    if verified != chain.overlay_assets:
        raise fail("creation.artifact_invalid", "图层素材在导出期间变化。", True)
    layers = tuple(
        ExportLayer(path.name, item.start_frame, item.end_frame, *canvas)
        for path, item in zip(paths, chain.overlays.items, strict=True)
    )
    dry_music_issue = None
    try:
        documents = _documents(
            jobs, chain, "timeline", tuple(_FILES), canvas, include_music, layers
        )
    except MusicTimelineError as error:
        if mix is None:
            raise fail("creation.input", str(error)) from error
        dry_music_issue = str(error)
        documents = _documents(jobs, chain, "timeline", tuple(_FILES), canvas, False, layers)
    mix_documents = (
        _documents(
            jobs, chain, "timeline-mix", ("fcpxml", "otio", "xmeml"), canvas, False, layers, mix
        )
        if mix is not None
        else {}
    )
    media_bytes = sum(path.stat().st_size for path in paths)
    document_bytes = sum(len(body) for body in (*documents.values(), *mix_documents.values()))
    if media_bytes > MAX_LAYER_BYTES or document_bytes > 32 * 1024**2:
        raise fail("creation.input", "专业交接包超出容量上限，请缩短或降低输出尺寸。")
    mix_bytes = mix_asset.stat().st_size if mix is not None else 0
    if shutil.disk_usage(directory).free < 256 * 1024**2 + media_bytes + mix_bytes + document_bytes:
        raise fail("creation.input", "本机剩余空间不足以写入专业交接包。")
    manifest: dict[str, object] = {
        "schemaVersion": "gamingcreator-timeline-handoff-v2"
        if mix
        else "gamingcreator-timeline-layers-v1",
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
    if mix_record is not None:
        manifest["referenceMix"] = mix_record
    if dry_music_issue is not None:
        manifest["dryMusicOmittedReason"] = dry_music_issue
    archive_path = directory / "timeline.zip"
    with ZipFile(archive_path, "x", compression=ZIP_STORED) as archive:
        for fmt, body in documents.items():
            archive.writestr("subtitles.srt" if fmt == "srt" else "timeline" + _FILES[fmt][0], body)
        for layer, path in zip(layers, paths, strict=True):
            archive.write(path, layer.url)
        if mix is not None:
            for fmt, body in mix_documents.items():
                archive.writestr("timeline-mix" + _FILES[fmt][0], body)
            archive.write(mix_asset, mix.path)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return archive_path


def _bundle_layer_media(
    jobs: CreationJobs, chain: Chain, directory: Path, canvas: tuple[int, int]
) -> tuple[Path, ...]:
    if not chain.overlays.items:
        return ()
    layer_directory = directory / "layers"
    layer_directory.mkdir()
    try:
        return asyncio.run(_render_layers(jobs, chain, layer_directory, canvas))
    except TimeoutError:
        raise AppError(
            "media.timeout", "图层交接处理超时，请缩短图层或降低输出尺寸。", ExitCode.ENVIRONMENT
        ) from None
    except ValueError as error:
        raise fail("creation.input", str(error)) from error


@contextmanager
def timeline_bundle(
    jobs: CreationJobs,
    project_id: str,
    job_id: str,
    plan_id: str,
    receipt: str,
    size: str,
    include_music: bool,
    reference: ReferenceRender | None = None,
) -> Iterator[tuple[Path, str]]:
    canvas = _size(size)
    chain = _saved_chain(jobs, job_id, plan_id)
    if chain.project_id != project_id or chain.digest != receipt:
        raise fail("creation.artifact_invalid", "保存版本已变化，请重开后导出。", True)
    if not chain.overlays.items and reference is None:
        raise fail("creation.input", "当前版本没有已保存的图层。")
    scratch = jobs.safe(jobs.root / "timeline-bundles")
    scratch.mkdir(exist_ok=True)
    jobs.safe(scratch / ".analysis-writer.lock")
    lock = ProjectWriterLock(scratch)
    lock.acquire()
    try:
        with TemporaryDirectory(prefix="layers-", dir=scratch) as temporary:
            archive = _archive_layers(
                jobs, chain, job_id, Path(temporary), canvas, include_music, reference
            )
            if _saved_chain(jobs, job_id, plan_id).digest != chain.digest:
                raise fail("creation.artifact_invalid", "保存版本在导出期间变化。", True)
            suffix = "mix" if reference else "layers"
            yield archive, f"gamingcreator-{job_id[:8]}-{suffix}.zip"
    finally:
        lock.close()
