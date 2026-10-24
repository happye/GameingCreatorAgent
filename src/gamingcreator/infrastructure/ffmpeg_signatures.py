"""Perceptual frame signatures through the project-local FFmpeg; never writes next to sources."""

import json
import re
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
    MIN_CROP_AREA_FRACTION,
    MIN_CROP_REMOVED_FRACTION,
    MIN_FRAME_STDEV,
    CropBox,
    choose_crop,
    frame_signature_pair,
)
from gamingcreator.infrastructure.media_process import run_media_process

SAMPLES_PER_SECOND = 2
FRAME_BYTES = HASH_WIDTH * HASH_HEIGHT
SAMPLING_FILTER = (
    f"fps={SAMPLES_PER_SECOND},scale={HASH_WIDTH}:{HASH_HEIGHT}:flags=area,format=gray"
)
CROP_DETECT_FILTER = "fps=1,cropdetect=limit=24:round=2:reset=0"
CROP_FILTER_TEMPLATE = "crop=W:H:X:Y"
_CROPDETECT_LINE = re.compile(r"cropdetect.*\scrop=(\d+):(\d+):(\d+):(\d+)\s*$")

IDENTITY = SignatureIdentity(
    f"dhash-{HASH_WIDTH}x{HASH_HEIGHT}-gray-v1",
    SAMPLING_FILTER,
    MIN_FRAME_STDEV,
    SAMPLES_PER_SECOND,
    CROP_DETECT_FILTER,
    CROP_FILTER_TEMPLATE,
    MIN_CROP_AREA_FRACTION,
    MIN_CROP_REMOVED_FRACTION,
    True,
)


def crop_filter(box: CropBox) -> str:
    """The filter text of ``CROP_FILTER_TEMPLATE`` for one box."""
    return f"crop={box.width}:{box.height}:{box.x}:{box.y}"


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

    async def detect_crop(
        self, source: Path, info: VideoStreamInfo, context: CancellationContext
    ) -> CropBox | None:
        """Content box over the whole video (union of every sampled frame), if it is adopted."""
        bounds: list[int] = []  # left, top, right, bottom of the union of all detected boxes

        def consume(line: str) -> bool:
            match = _CROPDETECT_LINE.search(line)
            if match is None:
                return False
            width, height, x, y = (int(value) for value in match.groups())
            if width > 0 and height > 0:
                box = [x, y, x + width, y + height]
                bounds[:] = (
                    box
                    if not bounds
                    else [
                        min(bounds[0], x),
                        min(bounds[1], y),
                        max(bounds[2], box[2]),
                        max(bounds[3], box[3]),
                    ]
                )
            return True

        await run_media_process(
            [
                str(self.tool_directory / "ffmpeg.exe"),
                "-hide_banner",
                "-nostdin",
                "-nostats",
                "-v",
                "info",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                CROP_DETECT_FILTER,
                "-f",
                "null",
                "-",
            ],
            context,
            stderr_line_consumer=consume,
        )
        if not bounds:
            return None
        return choose_crop(
            CropBox(bounds[2] - bounds[0], bounds[3] - bounds[1], bounds[0], bounds[1]),
            info.width,
            info.height,
            IDENTITY.min_crop_area_fraction,
            IDENTITY.min_crop_removed_fraction,
        )

    async def signature(
        self, source: Path, duration_us: int, context: CancellationContext
    ) -> SourceSignature:
        crop = await self.detect_crop(source, await self.video_info(source, context), context)
        sampling = SAMPLING_FILTER if crop is None else f"{crop_filter(crop)},{SAMPLING_FILTER}"
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
                    sampling,
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
        pairs = [
            frame_signature_pair(
                list(raw[offset : offset + FRAME_BYTES]),
                HASH_WIDTH,
                HASH_HEIGHT,
                MIN_FRAME_STDEV,
            )
            for offset in range(0, len(raw), FRAME_BYTES)
        ]
        return SourceSignature(
            tuple(normal for normal, _ in pairs),
            SAMPLES_PER_SECOND,
            tuple(mirrored for _, mirrored in pairs),
            crop,
        )
