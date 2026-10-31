"""Bounded two-input lossless composition on the shared frame layout."""

from fractions import Fraction
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderPlan
from gamingcreator.infrastructure.media_process import run_media_process
from gamingcreator.infrastructure.render_limits import render_output_limit


async def compose_transitions(
    ffmpeg: str,
    plan: RenderPlan,
    parts: list[Path],
    context: CancellationContext,
    width: int = 1280,
    height: int = 720,
) -> tuple[Path, list[Path]]:
    current = parts[0]
    temporary: list[Path] = []
    try:
        for index, part in enumerate(parts[1:], 1):
            overlap = plan.transition_frames[index]
            previous_frames = plan.start_frames[index - 1] + plan.clips[index - 1].output_frames
            frames = plan.start_frames[index] + plan.clips[index].output_frames
            samples = round(Fraction(frames * 48000, plan.fps))
            inputs = []
            for number, count in ((0, previous_frames), (1, plan.clips[index].output_frames)):
                inputs.extend(
                    [
                        f"[{number}:v]fps={plan.fps},settb=1/{plan.fps},setpts=N,format=yuv444p[v{number}]",
                        f"[{number}:a]aresample=48000,aformat=channel_layouts=stereo,"
                        f"apad,atrim=end_sample={round(Fraction(count * 48000, plan.fps))},asetpts=N/SR/TB[a{number}]",
                    ]
                )
            if overlap:
                inputs.extend(
                    [
                        f"[v0][v1]xfade=transition=fade:duration={overlap / plan.fps:.12f}:"
                        f"offset={(previous_frames - overlap) / plan.fps:.12f}[video]",
                        f"[a0][a1]acrossfade=ns={round(Fraction(overlap * 48000, plan.fps))}:c1=tri:c2=tri[audio]",
                    ]
                )
            else:
                inputs.extend(
                    [
                        "[v0][v1]concat=n=2:v=1:a=0[video]",
                        "[a0][a1]concat=n=2:v=0:a=1[audio]",
                    ]
                )
            inputs.extend(
                [
                    f"[video]tpad=stop_mode=clone:stop=-1,trim=end_frame={frames},"
                    f"settb=1/{plan.fps},setpts=N,format=yuv420p[v]",
                    f"[audio]apad,atrim=end_sample={samples},asetpts=N/SR/TB[a]",
                ]
            )
            output = part.parent / f"join-{index:06d}.nut"
            output_limit = render_output_limit(output, frames, plan.fps, width, height)
            temporary.append(output)
            await run_media_process(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-v",
                    "error",
                    "-nostdin",
                    "-n",
                    "-i",
                    str(current),
                    "-i",
                    str(part),
                    "-filter_complex_threads",
                    "1",
                    "-filter_complex",
                    ";".join(inputs),
                    "-map",
                    "[v]",
                    "-map",
                    "[a]",
                    "-c:v",
                    "ffv1",
                    "-c:a",
                    "pcm_s16le",
                    "-fs",
                    str(output_limit.max_bytes),
                    str(output),
                ],
                context,
                output_limit=output_limit,
            )
            current = output
    except BaseException:
        for path in temporary:
            path.unlink(missing_ok=True)
        raise
    return current, temporary
