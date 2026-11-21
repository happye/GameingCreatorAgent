"""Extract a sample-exact reference mix from a verified local render."""

import json
import wave
from contextlib import suppress
from fractions import Fraction
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure.local_paths import is_link
from gamingcreator.infrastructure.media_process import MediaOutputLimit, run_media_process

MAX_MIX_BYTES = 64 * 1024**2
_SAMPLE_RATE = 48_000
_PCM_FRAME_BYTES = 6
_AAC_TAIL_SAMPLES = 1024
_MOV_INPUT = ["-protocol_whitelist", "file", "-f", "mov"]


async def _decoded_samples(bin_dir: Path, source: Path, context: CancellationContext) -> int:
    result = await run_media_process(
        [
            str(bin_dir / "ffprobe.exe"),
            "-v",
            "error",
            *_MOV_INPUT,
            "-select_streams",
            "a:0",
            "-show_streams",
            "-show_frames",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,channel_layout,start_time,time_base:"
            "frame=best_effort_timestamp,nb_samples",
            "-of",
            "json=compact=1",
            str(source),
        ],
        context,
    )
    document = json.loads(result.stdout)
    streams = document.get("streams", [])
    if len(streams) != 1:
        raise ValueError("成片缺少可解码的首条音轨。")
    (stream,) = streams
    if (
        stream.get("codec_name") != "aac"
        or stream.get("sample_rate") != str(_SAMPLE_RATE)
        or stream.get("channels") != 2
        or stream.get("channel_layout") != "stereo"
        or Fraction(stream.get("start_time", "-1")) != 0
    ):
        raise ValueError("成片首条音轨必须是从零开始的 48 kHz 双声道 AAC。")
    samples = 0
    tick = Fraction(stream["time_base"]) * _SAMPLE_RATE
    for frame in document.get("frames", []):
        count = frame.get("nb_samples")
        timestamp = frame.get("best_effort_timestamp")
        if (
            type(count) is not int
            or count <= 0
            or type(timestamp) is not int
            or timestamp * tick != samples
        ):
            raise ValueError("成片音轨的解码时钟不连续。")
        samples += count
    if samples == 0:
        raise ValueError("成片首条音轨没有可用的音频样本。")
    return samples


def _verify_wav(path: Path, expected: int) -> None:
    with wave.open(str(path), "rb") as wav:
        if wav.getparams()[:5] != (2, 3, _SAMPLE_RATE, expected, "NONE"):
            raise ValueError("混音参考的采样数或 WAV 参数未通过校验。")
        remaining = expected
        while remaining:
            count = min(8192, remaining)
            if len(wav.readframes(count)) != count * _PCM_FRAME_BYTES:
                raise ValueError("混音参考 WAV 数据不完整。")
            remaining -= count


async def extract_render_mix(
    bin_dir: Path,
    source: Path,
    output: Path,
    frames: int,
    fps: int,
    context: CancellationContext,
) -> int:
    """Write a new WAV of the rounded output duration and return its PCM sample-frame count."""
    if type(frames) is not int or frames <= 0 or type(fps) is not int or fps <= 0:
        raise ValueError("混音参考需要有效的成片帧数和帧率。")
    expected = (frames * _SAMPLE_RATE + fps // 2) // fps
    if expected < 1 or expected * _PCM_FRAME_BYTES + 44 >= MAX_MIX_BYTES:
        raise ValueError("混音参考超过 64 MiB 或成片时长太短。")
    if output.exists() or is_link(output):
        raise ValueError("混音参考目标必须是新文件。")
    samples = await _decoded_samples(bin_dir, source, context)
    if abs(samples - expected) > _AAC_TAIL_SAMPLES:
        raise ValueError("成片音轨与画面时长不符，超出可裁补的 AAC 尾差。")
    filters = f"atrim=end_sample={expected}"
    if samples < expected:
        filters = f"apad=pad_len={expected - samples}," + filters
    budget = MediaOutputLimit(output, MAX_MIX_BYTES)
    try:
        await run_media_process(
            [
                str(bin_dir / "ffmpeg.exe"),
                "-v",
                "error",
                "-nostdin",
                "-n",
                *_MOV_INPUT,
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-sn",
                "-dn",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-af",
                filters,
                "-c:a",
                "pcm_s24le",
                "-ar",
                str(_SAMPLE_RATE),
                "-ac",
                "2",
                "-fs",
                str(MAX_MIX_BYTES),
                "-f",
                "wav",
                str(output),
            ],
            context,
            output_limit=budget,
        )
        _verify_wav(output, expected)
        context.check_cancelled()
    except BaseException:
        if not any(is_link(path) for path in (output, *output.parents)):
            with suppress(OSError):
                output.unlink(missing_ok=True)
        raise
    return expected
