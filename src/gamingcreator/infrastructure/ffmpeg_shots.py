"""Scene-change and black-frame evidence through the project-local FFmpeg; reads only."""

import re
from fractions import Fraction
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.shot_boundaries import ShotDetectorIdentity, ShotSamples
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import MediaAsset
from gamingcreator.domain.shot_boundaries import BlackTransition, CutCandidate
from gamingcreator.infrastructure.media_process import run_media_process

SCENE_THRESHOLD = 10
BLACK_PIXEL_THRESHOLD = "0.10"
SAMPLING_SCALE = "scale=320:180:flags=area"
# scdet's own log threshold is the maximum so only the metadata printers report; each
# printer emits a frame header line followed by its key, with integer pts in the stream
# time base (-copyts keeps the original clock, like media preparation).
SHOT_FILTER = (
    f"{SAMPLING_SCALE},scdet=threshold=100,blackdetect=d=0:pix_th={BLACK_PIXEL_THRESHOLD},"
    f"metadata=mode=print:key=lavfi.scd.score:value={SCENE_THRESHOLD}:function=greater,"
    "metadata=mode=print:key=lavfi.black_start,"
    "metadata=mode=print:key=lavfi.black_end"
)
IDENTITY = ShotDetectorIdentity(
    "ffmpeg-scdet-blackdetect-v1", SHOT_FILTER, SCENE_THRESHOLD, BLACK_PIXEL_THRESHOLD
)

_HEADER = re.compile(
    r"\[Parsed_metadata_\d+[^\]]*\]\s+frame:\s*\d+\s+pts:\s*(-?\d+)\s+pts_time:(\S+)"
)
_VALUE = re.compile(
    r"\[Parsed_metadata_\d+[^\]]*\]\s+lavfi\.(scd\.score|black_start|black_end)=(\S+)\s*$"
)
_CLOCK_TOLERANCE = Fraction(1, 100_000)
_ERROR = "画面切换时间戳与视频时钟不一致。"


class ShotLogParser:
    """Pairs each metadata header with its value and maps pts onto the source clock."""

    def __init__(self, asset: MediaAsset) -> None:
        video = next((item for item in asset.streams if item.kind == "video"), None)
        if video is None:
            raise AppError("media.shot_mapping", "素材没有视频流。", ExitCode.INPUT)
        self._asset = asset
        self._time_base = video.time_base
        self._pending: tuple[int, Fraction] | None = None
        self.cuts: list[CutCandidate] = []
        self.transitions: list[BlackTransition] = []
        self.outside = 0

    def consume(self, line: str) -> bool:
        header = _HEADER.search(line)
        if header is not None:
            pts = int(header.group(1))
            try:
                printed = Fraction(header.group(2))
            except ValueError:
                raise AppError("media.shot_mapping", _ERROR, ExitCode.INPUT) from None
            if abs(pts * self._time_base - printed) > _CLOCK_TOLERANCE:
                raise AppError("media.shot_mapping", _ERROR, ExitCode.INPUT)
            self._pending = (pts, printed)
            return True
        value = _VALUE.search(line)
        if value is None:
            return False
        if self._pending is None:
            raise AppError("media.shot_mapping", _ERROR, ExitCode.INPUT)
        pts, _ = self._pending
        self._pending = None
        seconds = pts * self._time_base - self._asset.origin_seconds
        if seconds < 0 or seconds * 1_000_000 >= self._asset.duration_us:
            self.outside += 1
            return True
        time_us = self._asset.instant(pts, self._time_base).time_us
        key, raw = value.groups()
        if key == "scd.score":
            try:
                score = float(raw)
            except ValueError:
                raise AppError("media.shot_mapping", _ERROR, ExitCode.INPUT) from None
            self.cuts.append(CutCandidate(time_us, score))
        else:
            self.transitions.append(BlackTransition(time_us, key == "black_start"))
        return True

    def finish(self) -> ShotSamples:
        if self._pending is not None:
            raise AppError("media.shot_mapping", _ERROR, ExitCode.INPUT)
        return ShotSamples(tuple(self.cuts), tuple(self.transitions), self.outside)


class FfmpegShotDetector:
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

    async def samples(self, asset: MediaAsset, context: CancellationContext) -> ShotSamples:
        video = next((item for item in asset.streams if item.kind == "video"), None)
        if video is None:
            raise AppError("media.shot_mapping", "素材没有视频流。", ExitCode.INPUT)
        parser = ShotLogParser(asset)
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
                "-copyts",
                "-i",
                str(asset.source_path),
                "-map",
                f"0:{video.index}",
                "-an",
                "-vf",
                SHOT_FILTER,
                "-fps_mode",
                "passthrough",
                "-f",
                "null",
                "-",
            ],
            context,
            stderr_line_consumer=parser.consume,
        )
        return parser.finish()
