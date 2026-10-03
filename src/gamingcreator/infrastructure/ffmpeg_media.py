import asyncio
import hashlib
import json
import os
import re
import wave
from fractions import Fraction
from pathlib import Path

from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import (
    AudioEvidence,
    AudioFrameMapping,
    MediaAsset,
    MediaPreprocessingResult,
    MediaStream,
    VisualEvidence,
    ceil_us,
)
from gamingcreator.infrastructure.local_files import LocalInputReader
from gamingcreator.infrastructure.media_process import run_media_process

TRANSFORM_VERSION = "ffmpeg-evidence-v1-piecewise-audio-trim"


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


async def hash_source(path: Path, context: CancellationContext) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            context.check_cancelled()
            digest.update(chunk)
            await asyncio.sleep(0)
    context.check_cancelled()
    return digest.hexdigest()


def _integer(value: object) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    raise ValueError("Missing integer metadata.")


def _fraction(value: object) -> Fraction:
    if not isinstance(value, str):
        raise ValueError("Missing rational metadata.")
    result = Fraction(value)
    if result <= 0:
        raise ValueError("Invalid stream clock.")
    return result


def parse_probe(raw: bytes, source: Path, source_hash: str, version: str) -> MediaAsset:
    try:
        data = json.loads(raw)
        streams = data["streams"]
        if not isinstance(streams, list):
            raise ValueError("No stream metadata.")
        selected: list[MediaStream] = []
        for kind in ("video", "audio"):
            candidates = [
                s
                for s in streams
                if isinstance(s, dict)
                and s.get("codec_type") == kind
                and not s.get("disposition", {}).get("attached_pic")
            ]
            if not candidates:
                continue
            stream = candidates[0]
            time_base = _fraction(stream.get("time_base"))
            start = _integer(stream.get("start_pts"))
            duration = _integer(stream.get("duration_ts"))
            selected.append(
                MediaStream(_integer(stream.get("index")), kind, time_base, start, duration)
            )
        origin = min(s.start_seconds for s in selected)
        duration_us = ceil_us(max(s.end_seconds for s in selected) - origin)
        return MediaAsset(
            source_hash, source, source_hash, tuple(selected), origin, duration_us, version
        )
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError):
        raise AppError(
            "input.media_timing", "视频流或精确时间元信息不可用。", ExitCode.INPUT
        ) from None


def parse_visual_log(log: str) -> tuple[Fraction, tuple[int, ...]]:
    clocks = re.findall(r"\[Parsed_showinfo_\d+[^\]]*\] config in time_base:\s*(\d+/\d+)", log)
    pts = tuple(
        int(p)
        for p in re.findall(
            r"\[Parsed_showinfo_\d+[^\]]*\]\s+n:\s*\d+\s+pts:\s*(-?\d+)\s+pts_time:", log
        )
    )
    if (
        len(set(clocks)) != 1
        or not pts
        or any(current <= previous for previous, current in zip(pts, pts[1:], strict=False))
    ):
        raise AppError("media.frame_mapping", "图片时间戳缺失、重复或倒退。", ExitCode.INPUT)
    return Fraction(clocks[0]), pts


def parse_audio_log(
    log: str, sample_rate: int, filter_name: str | None = None
) -> tuple[AudioFrameMapping, ...]:
    frames = []
    offset = 0
    prefix = (
        r"Parsed_ashowinfo_\d+" if filter_name is None else re.escape("ashowinfo@" + filter_name)
    )
    for pts, rate, samples in re.findall(
        r"\[" + prefix + r"[^\]]*\].*?\bpts:(-?\d+)\b.*?\brate:(\d+)\b.*?\bnb_samples:(\d+)\b", log
    ):
        if int(rate) != sample_rate:
            raise AppError("media.audio_mapping", "音频输出采样率不一致。", ExitCode.INPUT)
        frame = AudioFrameMapping(offset, int(samples), int(pts), Fraction(1, sample_rate))
        frames.append(frame)
        offset += frame.sample_count
    if not frames:
        raise AppError("media.audio_mapping", "音频样本映射缺失。", ExitCode.INPUT)
    return tuple(frames)


def _clock_json(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def write_manifest(result: MediaPreprocessingResult, parameters: SamplingParameters) -> None:
    asset = result.asset
    audio = result.audio
    coverage = None if audio is None else audio.map_interval(0, audio.sample_count, asset)
    payload = {
        "schemaVersion": 1,
        "status": "completed",
        "transformVersion": result.transform_version,
        "processorVersion": result.processor_version,
        "media": {
            "mediaId": asset.media_id,
            "sourcePath": str(asset.source_path),
            "sha256": asset.sha256,
            "originSeconds": _clock_json(asset.origin_seconds),
            "durationUs": asset.duration_us,
            "probeVersion": asset.probe_version,
            "streams": [
                {
                    "index": s.index,
                    "kind": s.kind,
                    "timeBase": _clock_json(s.time_base),
                    "startPts": s.start_pts,
                    "durationTs": s.duration_ts,
                }
                for s in asset.streams
            ],
        },
        "sampling": {
            "intervalSeconds": _clock_json(parameters.interval_seconds),
            "maxWidth": parameters.max_width,
            "maxFrames": parameters.max_frames,
        },
        "images": [
            {
                "evidenceId": image.evidence_id,
                "path": image.path.name,
                "sha256": image.sha256,
                "pts": image.pts,
                "timeBase": _clock_json(image.time_base),
                "sourceUs": image.source_time.time_us,
            }
            for image in result.images
        ],
        "audio": None
        if audio is None
        else {
            "evidenceId": audio.evidence_id,
            "path": audio.path.name,
            "sha256": audio.sha256,
            "sampleRate": audio.sample_rate,
            "sampleCount": audio.sample_count,
            "trimEndPts": audio.trim_end_pts,
            "decodedSampleCount": audio.decoded_sample_count,
            "samplesBeyondDeclaredEndRemoved": None
            if audio.decoded_sample_count is None
            else audio.decoded_sample_count - audio.sample_count,
            "discontinuityOffsets": audio.discontinuity_offsets,
            "boundaryToleranceSamples": 1,
            "coverage": None
            if coverage is None
            else {
                "startUs": coverage.source_range.start_us,
                "endUs": coverage.source_range.end_us,
                "clampedStartSeconds": _clock_json(coverage.clamped_start_seconds),
                "clampedEndSeconds": _clock_json(coverage.clamped_end_seconds),
            },
            "frames": [
                {
                    "sampleOffset": f.sample_offset,
                    "sampleCount": f.sample_count,
                    "pts": f.pts,
                    "timeBase": _clock_json(f.time_base),
                }
                for f in audio.frames
            ],
        },
    }
    temporary = result.manifest_path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as destination:
        json.dump(payload, destination, ensure_ascii=False, separators=(",", ":"))
        destination.flush()
        os.fsync(destination.fileno())
    temporary.replace(result.manifest_path)


class FfmpegMediaProcessor:
    def __init__(self, repository: Path) -> None:
        self.tool_directory = repository.resolve() / ".tools" / "ffmpeg" / "bin"

    async def probe(self, source: Path, context: CancellationContext) -> MediaAsset:
        source = LocalInputReader().validate_video(source)
        context.check_cancelled()
        try:
            source_hash = await hash_source(source, context)
        except OSError:
            raise AppError("input.video", "无法读取源媒体文件。", ExitCode.INPUT) from None
        probe = str(self.tool_directory / "ffprobe.exe")
        version = await run_media_process([probe, "-version"], context)
        output = await run_media_process(
            [
                probe,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(source),
            ],
            context,
        )
        return parse_probe(
            output.stdout,
            source,
            source_hash,
            version.stdout.decode("utf-8", "replace").splitlines()[0],
        )

    async def preprocess(
        self,
        source: Path,
        output: Path,
        parameters: SamplingParameters,
        context: CancellationContext,
    ) -> MediaPreprocessingResult:
        asset = await self.probe(source, context)
        context.check_cancelled()
        source = asset.source_path
        ffmpeg = str(self.tool_directory / "ffmpeg.exe")
        version_output = await run_media_process([ffmpeg, "-version"], context)
        version_lines = version_output.stdout.decode("utf-8", "replace").splitlines()
        if not version_lines:
            raise AppError("environment.media_tool", "媒体工具版本不可用。", ExitCode.ENVIRONMENT)
        if output.resolve() == source.parent or output.exists():
            raise AppError("input.media_output", "媒体输出须使用新的独立目录。", ExitCode.INPUT)
        try:
            output.mkdir(parents=True, exist_ok=False)
            video = next(s for s in asset.streams if s.kind == "video")
            common = [
                ffmpeg,
                "-hide_banner",
                "-nostdin",
                "-y",
                "-protocol_whitelist",
                "file,pipe",
                "-copyts",
                "-i",
                str(source),
            ]
            interval = (
                f"{parameters.interval_seconds.numerator}/{parameters.interval_seconds.denominator}"
            )
            filters = f"select='isnan(prev_selected_t)+gte(t-prev_selected_t,{interval})',scale=w='min({parameters.max_width},iw)':h=-2,showinfo"
            frames_output = await run_media_process(
                [
                    *common,
                    "-map",
                    f"0:{video.index}",
                    "-an",
                    "-vf",
                    filters,
                    "-fps_mode",
                    "passthrough",
                    "-frames:v",
                    str(parameters.max_frames + 1),
                    str(output / "frame-%06d.jpg"),
                ],
                context,
            )
            time_base, pts = parse_visual_log(frames_output.stderr.decode("utf-8", "replace"))
            images = sorted(output.glob("frame-*.jpg"))
            if len(images) != len(pts) or len(images) > parameters.max_frames:
                raise AppError(
                    "media.frame_limit", "抽帧数量不一致或超过配置上限。", ExitCode.INPUT
                )
            if abs(pts[0] * time_base - video.start_seconds) > video.time_base:
                raise AppError("media.stream_start", "首帧与媒体流起点不一致。", ExitCode.INPUT)
            evidence = tuple(
                VisualEvidence(
                    f"{context.run_id}:{asset.media_id}:image:{index:06d}",
                    path,
                    hash_file(path),
                    timestamp,
                    time_base,
                    asset.instant(timestamp, time_base),
                )
                for index, (path, timestamp) in enumerate(zip(images, pts, strict=True))
            )
            audio_stream = next((s for s in asset.streams if s.kind == "audio"), None)
            audio = None
            if audio_stream is not None:
                audio_path = output / "audio.wav"
                sample_rate = 16000
                trim_end_pts = (audio_stream.end_seconds * sample_rate).__ceil__()
                audio_filters = f"aresample=16000,aformat=channel_layouts=mono,ashowinfo@decoded,atrim=end_pts={trim_end_pts},ashowinfo@mapped"
                audio_output = await run_media_process(
                    [
                        *common,
                        "-map",
                        f"0:{audio_stream.index}",
                        "-vn",
                        "-af",
                        audio_filters,
                        "-ac",
                        "1",
                        "-c:a",
                        "pcm_s16le",
                        str(audio_path),
                    ],
                    context,
                )
                audio_log = audio_output.stderr.decode("utf-8", "replace")
                mapping = parse_audio_log(audio_log, sample_rate, "mapped")
                decoded = parse_audio_log(audio_log, sample_rate, "decoded")
                with wave.open(str(audio_path), "rb") as wav:
                    if (
                        wav.getnchannels() != 1
                        or wav.getframerate() != sample_rate
                        or wav.getsampwidth() != 2
                    ):
                        raise AppError(
                            "media.audio_format", "音频输出格式不符合合同。", ExitCode.INPUT
                        )
                    audio = AudioEvidence(
                        f"{context.run_id}:{asset.media_id}:audio:000000",
                        audio_path,
                        hash_file(audio_path),
                        sample_rate,
                        wav.getnframes(),
                        mapping,
                        trim_end_pts,
                        sum(frame.sample_count for frame in decoded),
                    )
                if (
                    abs(mapping[0].pts * mapping[0].time_base - audio_stream.start_seconds)
                    > Fraction(1, sample_rate) + audio_stream.time_base
                ):
                    raise AppError(
                        "media.stream_start", "音频首样本与媒体流起点不一致。", ExitCode.INPUT
                    )
                audio.map_interval(0, audio.sample_count, asset)
            context.check_cancelled()
            try:
                current_source_hash = await hash_source(source, context)
            except OSError:
                raise AppError(
                    "media.source_changed", "处理期间源文件不可读取。", ExitCode.INPUT
                ) from None
            if current_source_hash != asset.sha256:
                raise AppError("media.source_changed", "处理期间源文件发生变化。", ExitCode.INPUT)
            context.check_cancelled()
            result = MediaPreprocessingResult(
                asset,
                evidence,
                audio,
                output / "media-manifest.json",
                TRANSFORM_VERSION,
                version_lines[0],
            )
            write_manifest(result, parameters)
            return result
        except (OSError, wave.Error):
            raise AppError(
                "storage.media_output", "无法写入或核验媒体输出。", ExitCode.STORAGE
            ) from None
        except ValueError:
            raise AppError("media.mapping", "媒体时间或产物映射无效。", ExitCode.INPUT) from None
