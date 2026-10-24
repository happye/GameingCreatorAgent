"""Perceptual frame signatures through the project-local FFmpeg; never writes next to sources."""

import json
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.source_inventory import (
    SignatureIdentity,
    SourceSignature,
    VideoStreamInfo,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.footage_overlap import (
    HASH_HEIGHT,
    HASH_WIDTH,
    MIN_FRAME_STDEV,
    frame_signature,
)
from gamingcreator.infrastructure.media_process import run_media_process

SAMPLES_PER_SECOND = 2
FRAME_BYTES = HASH_WIDTH * HASH_HEIGHT
SAMPLING_FILTER = (
    f"fps={SAMPLES_PER_SECOND},scale={HASH_WIDTH}:{HASH_HEIGHT}:flags=area,format=gray"
)


IDENTITY = SignatureIdentity(
    f"dhash-{HASH_WIDTH}x{HASH_HEIGHT}-gray-v1",
    SAMPLING_FILTER,
    MIN_FRAME_STDEV,
    SAMPLES_PER_SECOND,
)


class FfmpegSignatureExtractor:
    identity = IDENTITY

    def __init__(self, repository: Path) -> None:
        self.tool_directory = repository.resolve() / ".tools" / "ffmpeg" / "bin"

    async def tool_version(self, context: CancellationContext) -> str:
        output = await run_media_process(
            [str(self.tool_directory / "ffmpeg.exe"), "-version"], context
        )
        lines = output.stdout.decode("utf-8", "replace").splitlines()
        if not lines:
            raise AppError("environment.media_tool", "媒体工具版本不可用。", ExitCode.ENVIRONMENT)
        return lines[0]

    async def video_info(self, source: Path, context: CancellationContext) -> VideoStreamInfo:
        output = await run_media_process(
            [
                str(self.tool_directory / "ffprobe.exe"),
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-select_streams",
                "v:0",
                "-show_streams",
                "-of",
                "json",
                str(source),
            ],
            context,
        )
        try:
            streams = json.loads(output.stdout)["streams"]
            stream = streams[0]
            codec, rate = stream["codec_name"], stream["avg_frame_rate"]
            width, height = stream["width"], stream["height"]
            if (
                not isinstance(codec, str)
                or not isinstance(rate, str)
                or type(width) is not int
                or type(height) is not int
                or width <= 0
                or height <= 0
            ):
                raise ValueError
            return VideoStreamInfo(codec, width, height, rate)
        except (ValueError, TypeError, KeyError, IndexError):
            raise AppError("input.media_timing", "视频流元信息不可用。", ExitCode.INPUT) from None

    async def signature(
        self, source: Path, duration_us: int, context: CancellationContext
    ) -> SourceSignature:
        expected = duration_us // 1_000_000 * SAMPLES_PER_SECOND + 16
        raw = (
            await run_media_process(
                [
                    str(self.tool_directory / "ffmpeg.exe"),
                    "-hide_banner",
                    "-nostdin",
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-i",
                    str(source),
                    "-map",
                    "0:v:0",
                    "-an",
                    "-vf",
                    SAMPLING_FILTER,
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "gray",
                    "pipe:1",
                ],
                context,
                max_stdout_bytes=expected * FRAME_BYTES,
            )
        ).stdout
        if not raw or len(raw) % FRAME_BYTES:
            raise AppError("media.signature", "无法取得视频画面签名。", ExitCode.INPUT)
        hashes = tuple(
            frame_signature(
                list(raw[offset : offset + FRAME_BYTES]),
                HASH_WIDTH,
                HASH_HEIGHT,
                MIN_FRAME_STDEV,
            )
            for offset in range(0, len(raw), FRAME_BYTES)
        )
        return SourceSignature(hashes, SAMPLES_PER_SECOND)
