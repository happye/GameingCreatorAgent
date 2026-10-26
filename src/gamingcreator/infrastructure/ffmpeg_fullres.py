"""Native-resolution copies of a run's sampled frames through the project-local FFmpeg.

Repeats media preparation's frame selection (same filter, ``-copyts`` and passthrough
timing) without scaling, into a scratch directory outside the project. The caller compares
the returned timestamps with the saved evidence instants before using any image.
"""

from fractions import Fraction
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.media import MediaAsset
from gamingcreator.infrastructure.ffmpeg_media import VisualLogParser
from gamingcreator.infrastructure.media_process import run_media_process


def selection_filter(interval_seconds: Fraction) -> str:
    """Media preparation's selection, minus its scaling: one frame per interval."""
    interval = f"{interval_seconds.numerator}/{interval_seconds.denominator}"
    return f"select='isnan(prev_selected_t)+gte(t-prev_selected_t,{interval})',showinfo"


class FfmpegFullResolutionFrames:
    def __init__(self, repository: Path) -> None:
        self.tool_directory = repository.resolve() / ".tools" / "ffmpeg" / "bin"

    async def extract(
        self,
        asset: MediaAsset,
        interval_seconds: Fraction,
        count: int,
        output: Path,
        context: CancellationContext,
    ) -> tuple[tuple[int, Fraction, Path], ...]:
        """(pts, time base, image) for the first ``count`` selected frames, in order."""
        video = next((item for item in asset.streams if item.kind == "video"), None)
        if video is None or count <= 0:
            raise AppError("media.frame_mapping", "素材没有可取的视频帧。", ExitCode.INPUT)
        if output.exists():
            raise AppError("input.media_output", "原分辨率帧须使用新的独立目录。", ExitCode.INPUT)
        output.mkdir(parents=True)
        parser = VisualLogParser()
        await run_media_process(
            [
                str(self.tool_directory / "ffmpeg.exe"),
                "-hide_banner",
                "-nostdin",
                "-y",
                "-protocol_whitelist",
                "file,pipe",
                "-copyts",
                "-i",
                str(asset.source_path),
                "-map",
                f"0:{video.index}",
                "-an",
                "-vf",
                selection_filter(interval_seconds),
                "-fps_mode",
                "passthrough",
                "-frames:v",
                str(count),
                "-q:v",
                "2",
                str(output / "frame-%06d.jpg"),
            ],
            context,
            stderr_line_consumer=parser.consume,
        )
        time_base, pts = parser.finish()
        images = sorted(output.glob("frame-*.jpg"))
        if len(images) != len(pts):
            raise AppError("media.frame_mapping", "原分辨率帧与时间戳数量不一致。", ExitCode.INPUT)
        return tuple((value, time_base, image) for value, image in zip(pts, images, strict=True))
