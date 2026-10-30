"""Fixed local FFmpeg renderer, preserving source clocks and publishing receipt last."""

import json
from fractions import Fraction
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.creation_subtitles import SubtitleCue, parse_srt, serialize_srt
from gamingcreator.infrastructure.ffmpeg_media import hash_source
from gamingcreator.infrastructure.local_paths import is_link, resolve_existing
from gamingcreator.infrastructure.media_process import run_media_process


def clip_filter(clip: RenderClip, fps: int, width: int, height: int) -> str:
    start = clip.asset.origin_seconds + Fraction(clip.source_range.start_us, 1_000_000)
    end = clip.asset.origin_seconds + Fraction(clip.source_range.end_us, 1_000_000)
    video = next(stream for stream in clip.asset.streams if stream.kind == "video")
    first = (start / video.time_base).__ceil__()
    last = (end / video.time_base).__ceil__()
    duration = Fraction(clip.output_frames, fps)
    # copyts keeps the asset's original stream PTS; setpts maps its source origin to output zero.
    vf = (
        f"[0:{video.index}]trim=start_pts={first}:end_pts={last},"
        f"setpts=PTS-({start.numerator}/{start.denominator})/TB,"
        f"fps={fps}:start_time=0,scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,"
        f"tpad=stop_mode=clone:stop_duration=1,trim=end_frame={clip.output_frames},"
        "setpts=N/FRAME_RATE/TB[v]"
    )
    audio = next((stream for stream in clip.asset.streams if stream.kind == "audio"), None)
    if audio is None:
        af = "anullsrc=r=48000:cl=stereo"
    else:
        af = (
            f"[0:{audio.index}]atrim=start_pts={(start / audio.time_base).__ceil__()}:"
            f"end_pts={(end / audio.time_base).__ceil__()},"
            f"asetpts=PTS-({start.numerator}/{start.denominator})/TB,"
            "aresample=48000:async=1:first_pts=0,aformat=channel_layouts=stereo,apad"
        )
    return vf + ";" + af + f",atrim=duration={float(duration):.12f},asetpts=N/SR/TB[a]"


def _burn_ass(cues: tuple[SubtitleCue, ...], width: int, height: int) -> str:
    # Never interpret transcript text as ASS override commands.
    header = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Arial,{max(12, height // 18)},&H00FFFFFF,&H00FFFFFF,&H00000000,"
        "&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,4,4,4,1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    def clock(time: Fraction) -> str:
        seconds, cs = divmod((time * 100).__floor__(), 100)
        minutes, sec = divmod(seconds, 60)
        hours, minute = divmod(minutes, 60)
        return f"{hours}:{minute:02d}:{sec:02d}.{cs:02d}"

    for cue in cues:
        if clock(cue.start) == clock(cue.end):
            continue
        text = cue.text.translate(str.maketrans("\\{}", "＼｛｝")).replace("\n", r"\N")
        header += f"Dialogue: 0,{clock(cue.start)},{clock(cue.end)},Default,,0,0,0,,{text}\n"
    return header


def _filter_path(path: Path) -> str:
    value = path.as_posix()
    value = value.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    return "".join("\\" + char if char in "\\'[],;" else char for char in value)


class FfmpegCreationRenderer:
    def __init__(self, repository: Path) -> None:
        self.bin = repository.resolve() / ".tools/ffmpeg/bin"

    async def render(
        self,
        plan: RenderPlan,
        output: Path,
        protected: tuple[Path, ...],
        context: CancellationContext,
        width: int = 1280,
        height: int = 720,
        creation_digest: str = "",
        cues: tuple[SubtitleCue, ...] = (),
        subtitle_mode: str = "none",
    ) -> dict[str, object]:
        if subtitle_mode not in ("none", "sidecar", "burn"):
            raise ValueError("Unknown subtitle mode.")
        subtitle_text = serialize_srt(cues) if subtitle_mode != "none" else ""
        saved_cues = parse_srt(subtitle_text)
        if any(cue.end > Fraction(plan.frames, plan.fps) for cue in saved_cues):
            raise ValueError("Subtitle extends beyond render output.")
        if any(
            type(value) is not int or not 16 <= value <= 3840 or value % 2
            for value in (width, height)
        ):
            raise ValueError("Render dimensions must be even integers in 16..3840.")
        target = resolve_existing(output)
        if is_link(output) or any(
            target == resolve_existing(path) or target.is_relative_to(resolve_existing(path))
            for path in protected
        ):
            raise ValueError("Render output must be outside all input paths.")
        context.check_cancelled()
        target.mkdir(parents=True, exist_ok=False)
        subtitle_path = target / "subtitles.srt"
        ass_path = target / "subtitles.ass"
        video_filter = f"fps={plan.fps}"
        if subtitle_mode != "none":
            with subtitle_path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(subtitle_text)
        if subtitle_mode == "burn" and saved_cues:
            ass_path.write_text(_burn_ass(saved_cues, width, height), encoding="utf-8")
            video_filter += f",ass=filename={_filter_path(ass_path)}"
        ffmpeg = str(self.bin / "ffmpeg.exe")
        parts: list[Path] = []
        for index, clip in enumerate(plan.clips):
            part = target / f"part-{index:06d}.nut"
            await run_media_process(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-v",
                    "error",
                    "-nostdin",
                    "-n",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-copyts",
                    "-i",
                    str(clip.asset.source_path),
                    "-filter_complex",
                    clip_filter(clip, plan.fps, width, height),
                    "-map",
                    "[v]",
                    "-map",
                    "[a]",
                    "-c:v",
                    "ffv1",
                    "-c:a",
                    "pcm_s16le",
                    str(part),
                ],
                context,
            )
            parts.append(part)
        manifest = target / "parts.txt"
        manifest.write_text("".join(f"file '{part.name}'\n" for part in parts), encoding="utf-8")
        pending = target / "render.partial.mp4"
        await run_media_process(
            [
                ffmpeg,
                "-hide_banner",
                "-v",
                "error",
                "-nostdin",
                "-n",
                "-protocol_whitelist",
                "file,pipe",
                "-f",
                "concat",
                "-safe",
                "1",
                "-i",
                str(manifest),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-vf",
                video_filter,
                "-frames:v",
                str(plan.frames),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-movflags",
                "+faststart",
                str(pending),
            ],
            context,
        )
        probed = await run_media_process(
            [
                str(self.bin / "ffprobe.exe"),
                "-v",
                "error",
                "-count_frames",
                "-show_streams",
                "-of",
                "json",
                str(pending),
            ],
            context,
        )
        streams = json.loads(probed.stdout)["streams"]
        video = next(stream for stream in streams if stream["codec_type"] == "video")
        audio = next(stream for stream in streams if stream["codec_type"] == "audio")
        expected = Fraction(plan.frames, plan.fps)
        actual = int(video["duration_ts"]) * Fraction(video["time_base"])
        if int(video["nb_read_frames"]) != plan.frames or abs(actual - expected) > Fraction(
            1, plan.fps
        ):
            raise ValueError("Rendered frame count or duration differs from the editing decision.")
        await run_media_process(
            [ffmpeg, "-v", "error", "-xerror", "-nostdin", "-i", str(pending), "-f", "null", "-"],
            context,
        )
        for asset in {
            (resolve_existing(clip.asset.source_path), clip.asset.sha256): clip.asset
            for clip in plan.clips
        }.values():
            if await hash_source(asset.source_path, context) != asset.sha256:
                raise ValueError("Source changed during rendering.")
        context.check_cancelled()
        final = target / "video.mp4"
        pending.rename(final)
        digest = await hash_source(final, context)
        files = {"video.mp4": digest}
        if subtitle_mode != "none":
            files["subtitles.srt"] = await hash_source(subtitle_path, context)
        result: dict[str, object] = {
            "schemaVersion": "creation-render-receipt-v1",
            "status": "completed",
            "creationReceiptSha256": creation_digest,
            "files": files,
            "subtitles": {"mode": subtitle_mode, "cueCount": len(saved_cues)},
            "frames": plan.frames,
            "fpsNumerator": plan.fps,
            "fpsDenominator": 1,
            "width": width,
            "height": height,
            "videoDuration": str(actual),
            "audioStartSeconds": audio.get("start_time"),
            "audioPolicy": "source-clock-resample-or-silence-48000-stereo",
            "limitations": [
                "hard cuts",
                "letterbox",
                "no overlays, transitions or speed changes",
                "burn uses centisecond timing and visible fullwidth ASS control characters",
            ],
        }
        # Remove only our deterministic temporary files, after validation, before completion.
        for part in parts:
            part.unlink()
        manifest.unlink()
        if ass_path.exists():
            ass_path.unlink()
        context.check_cancelled()
        with (target / "receipt.partial.json").open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        context.check_cancelled()
        (target / "receipt.partial.json").rename(target / "receipt.json")
        return {"output": str(target), "video": str(final), **result}
