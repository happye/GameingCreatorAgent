"""Fixed local FFmpeg renderer, preserving source clocks and publishing receipt last."""

import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

from gamingcreator.application.narration import NarrationArtifact
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderClip, RenderPlan
from gamingcreator.domain.creation_audio import AudioMix
from gamingcreator.domain.creation_narration import NarrationSelection, validate_narration_fit
from gamingcreator.domain.creation_subtitles import SubtitleCue, parse_srt, serialize_srt
from gamingcreator.infrastructure.crossfade_render import compose_transitions
from gamingcreator.infrastructure.ffmpeg_media import hash_source
from gamingcreator.infrastructure.local_paths import is_link, resolve_existing
from gamingcreator.infrastructure.media_process import run_media_process
from gamingcreator.infrastructure.music_library import _FORMATS, MusicTrack
from gamingcreator.infrastructure.narration_mix import (
    narration_filter,
    narration_receipt,
    verify_narration,
)
from gamingcreator.infrastructure.render_limits import render_output_limit


def clip_filter(clip: RenderClip, fps: int, width: int, height: int) -> str:
    start = clip.asset.origin_seconds + Fraction(clip.source_range.start_us, 1_000_000)
    end = clip.asset.origin_seconds + Fraction(clip.source_range.end_us, 1_000_000)
    video = next(stream for stream in clip.asset.streams if stream.kind == "video")
    first = (start / video.time_base).__ceil__()
    last = (end / video.time_base).__ceil__()
    duration = Fraction(clip.output_frames, fps)
    speed_filter = (
        "" if clip.speed == 1 else f"setpts=PTS*{clip.speed.denominator}/{clip.speed.numerator},"
    )
    # copyts keeps the asset's original stream PTS; setpts maps its source origin to output zero.
    vf = (
        f"[0:{video.index}]trim=start_pts={first}:end_pts={last},"
        f"setpts=PTS-({start.numerator}/{start.denominator})/TB,"
        f"{speed_filter}fps={fps}:start_time=0,scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,"
        f"tpad=stop_mode=clone:stop=-1,trim=end_frame={clip.output_frames},"
        "setpts=N/FRAME_RATE/TB[v]"
    )
    audio = next((stream for stream in clip.asset.streams if stream.kind == "audio"), None)
    if (
        audio is not None
        and clip.speed != 1
        and (audio.start_seconds >= end or audio.end_seconds <= start)
    ):
        audio = None
    if audio is None:
        af = "anullsrc=r=48000:cl=stereo"
    else:
        af = (
            # Decoder audio filter PTS use the sample clock, not necessarily the
            # container stream time base (e.g. Matroska PCM uses millisecond packets).
            f"[0:{audio.index}]atrim=start={float(start):.12f}:end={float(end):.12f},"
            f"asetpts=PTS-({start.numerator}/{start.denominator})/TB,"
            "aresample=48000:async=1:first_pts=0,aformat=channel_layouts=stereo,apad"
        )
    if audio is not None and clip.speed != 1:
        # Fill source-clock gaps and the source tail before tempo conversion.
        source_duration = Fraction(clip.source_range.end_us - clip.source_range.start_us, 1_000_000)
        delay = min(max(audio.start_seconds - start, Fraction(0)), source_duration)
        # Tempo windows can smear a leading silent gap. Preserve the known stream
        # delay explicitly on the output sample clock instead of stretching silence.
        af += (
            f",atrim=start={float(delay):.12f}:end={float(source_duration):.12f},"
            f"asetpts=N/SR/TB,atempo={float(clip.speed):.12f},"
            f"adelay={round(delay / clip.speed * 48000)}S:all=1,apad"
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

    # Split only at overlap edges. Earlier clips lift above later clips while
    # both are visible; outside those intervals every cue uses the bottom lane.
    for cue in cues:
        edges = {cue.start, cue.end}
        others = [
            other
            for other in cues
            if other is not cue
            and other.clip_index != cue.clip_index
            and other.start < cue.end
            and cue.start < other.end
        ]
        for other in others:
            edges.update((max(cue.start, other.start), min(cue.end, other.end)))
        boundaries = sorted(edges)
        for start, end in zip(boundaries, boundaries[1:], strict=False):
            if clock(start) == clock(end):
                continue
            lifted = any(
                other.start < end
                and start < other.end
                and (cue.clip_index or 0) < (other.clip_index or 0)
                for other in others
            )
            margin = max(24, height // 8) if lifted else 4
            text = cue.text.translate(str.maketrans("\\{}", "＼｛｝")).replace("\n", r"\N")
            header += f"Dialogue: 0,{clock(start)},{clock(end)},Default,,0,0,{margin},,{text}\n"
    return header


def _filter_path(path: Path) -> str:
    value = path.as_posix()
    value = value.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    return "".join("\\" + char if char in "\\'[],;" else char for char in value)


def _mix_filter(mix: AudioMix, frames: int, fps: int, output: str = "mixed") -> str:
    duration = f"{frames / fps:.12f}"
    source = f"[0:a:0]volume={mix.source_gain_db}dB[src]"
    if mix.bgm is None:
        return source + f";[src]anull[{output}]"
    music = (
        "[1:a:0]aresample=48000,aformat=channel_layouts=stereo,"
        f"asetpts=N/SR/TB,atrim=duration={duration},volume={mix.bgm.gain_db}dB[bgm]"
    )
    if mix.ducking == "source-v1":
        # Measure unattenuated source: lowering game volume must not disable ducking.
        source = f"[0:a:0]asplit=2[raw][key];[raw]volume={mix.source_gain_db}dB[src]"
        music += (
            ";[bgm][key]sidechaincompress=threshold=0.015:ratio=12:attack=10:"
            "release=200:makeup=1:knee=1:detection=rms[ducked]"
        )
        label = "ducked"
    else:
        label = "bgm"
    return (
        source + ";" + music + f";[src][{label}]amix=inputs=2:duration=first:"
        "dropout_transition=0:normalize=0,alimiter=limit=0.95:level=false:"
        f"latency=true,atrim=duration={duration}[{output}]"
    )


async def _verify_music(music: MusicTrack, context: CancellationContext) -> None:
    receipt = music.path.parent / "receipt.json"
    if (
        str(music.path).startswith("\\\\")
        or ":" in music.path.name
        or music.path.name not in {"audio" + suffix for suffix in _FORMATS}
        or music.path.parent.name != music.track_id
    ):
        raise ValueError("Invalid local registered music path.")
    if any(is_link(path) for path in (music.path, receipt, *music.path.parents)):
        raise ValueError("Music paths must not contain links.")
    if await hash_source(music.path, context) != music.sha256:
        raise ValueError("Music media hash mismatch.")
    if await hash_source(receipt, context) != music.receipt_sha256:
        raise ValueError("Music receipt hash mismatch.")


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
        audio_mix: AudioMix | None = None,
        music: MusicTrack | None = None,
        narration: NarrationSelection | None = None,
        narration_artifact: NarrationArtifact | None = None,
    ) -> dict[str, object]:
        mix = audio_mix if audio_mix is not None else AudioMix()
        # Re-parse even constructed dataclasses, so bool/non-finite gains fail closed.
        mix = AudioMix.from_json(mix.to_json())
        if mix.bgm is not None:
            if music is None or (
                music.track_id != mix.bgm.track_id
                or music.receipt_sha256 != mix.bgm.track_receipt_sha256
            ):
                raise ValueError("Music selection identity mismatch.")
            await _verify_music(music, context)
            protected = (*protected, music.path.parent)
        elif music is not None:
            raise ValueError("Music supplied without a BGM selection.")
        if (narration is None) != (narration_artifact is None):
            raise ValueError("Narration selection and verified asset must be supplied together.")
        if narration is not None and narration_artifact is not None:
            narration = NarrationSelection.from_json(narration.to_json())
            narration_artifact = verify_narration(narration, narration_artifact)
            validate_narration_fit(
                narration,
                narration_artifact.sample_count,
                narration_artifact.sample_rate,
                plan.frames,
                plan.fps,
            )
            protected = (*protected, narration_artifact.directory)
        if subtitle_mode not in ("none", "sidecar", "burn"):
            raise ValueError("Unknown subtitle mode.")
        subtitle_text = serialize_srt(cues) if subtitle_mode != "none" else ""
        # SRT order is deterministic; carry identities by record position after quantization.
        ordered = sorted(cues, key=lambda cue: (cue.start, cue.end))
        identities = [
            cue for cue in ordered if (cue.start * 1000).__floor__() < (cue.end * 1000).__floor__()
        ]
        saved_cues = (
            tuple(
                replace(saved, clip_index=original.clip_index)
                for saved, original in zip(parse_srt(subtitle_text), identities, strict=True)
            )
            if subtitle_mode != "none"
            else ()
        )
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
        # The final fps filter needs an EOF frame beyond the last presentation
        # instant; cap by frames after padding, rather than stopping the muxer early.
        video_filter = (
            f"tpad=stop_mode=clone:stop_duration=1,fps={plan.fps},"
            f"trim=end_frame={plan.frames},setpts=N/FRAME_RATE/TB"
        )
        if subtitle_mode != "none":
            with subtitle_path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(subtitle_text)
        if subtitle_mode == "burn" and saved_cues:
            ass_path.write_text(_burn_ass(saved_cues, width, height), encoding="utf-8")
            video_filter += f",ass=filename={_filter_path(ass_path)}"
        ffmpeg = str(self.bin / "ffmpeg.exe")
        parts: list[Path] = []
        try:
            for index, clip in enumerate(plan.clips):
                part = target / f"part-{index:06d}.nut"
                part_limit = render_output_limit(part, clip.output_frames, plan.fps, width, height)
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
                        "-fs",
                        str(part_limit.max_bytes),
                        str(part),
                    ],
                    context,
                    output_limit=part_limit,
                )
                parts.append(part)
            manifest = target / "parts.txt"
            manifest.write_text(
                "".join(
                    f"file '{part.name}'\nduration {clip.output_frames / plan.fps:.12f}\n"
                    for part, clip in zip(parts, plan.clips, strict=True)
                ),
                encoding="utf-8",
            )
            joined_parts: list[Path] = []
            input_args = ["-f", "concat", "-safe", "1", "-i", str(manifest)]
            if any(plan.transition_frames):
                joined, joined_parts = await compose_transitions(
                    ffmpeg, plan, parts, context, width, height
                )
                input_args = ["-i", str(joined)]
            has_mix = mix.bgm is not None or mix.source_gain_db != 0 or narration is not None
            audio_filter = _mix_filter(mix, plan.frames, plan.fps, "bed" if narration else "mixed")
            if narration is not None:
                audio_filter += ";" + narration_filter(
                    narration, plan.frames, plan.fps, 2 if music is not None else 1
                )
            try:
                pending = target / "render.partial.mp4"
                final_limit = render_output_limit(pending, plan.frames, plan.fps, width, height)
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
                        *input_args,
                        *(
                            [
                                "-protocol_whitelist",
                                "file",
                                "-f",
                                _FORMATS[music.path.suffix],
                                "-stream_loop",
                                "-1",
                                "-i",
                                str(music.path),
                            ]
                            if music is not None
                            else []
                        ),
                        *(
                            [
                                "-protocol_whitelist",
                                "file",
                                "-f",
                                "wav",
                                "-i",
                                str(narration_artifact.wav_path),
                            ]
                            if narration_artifact is not None
                            else []
                        ),
                        *(["-filter_complex", audio_filter] if has_mix else []),
                        "-map",
                        "0:v:0",
                        "-map",
                        "[mixed]" if has_mix else "0:a:0",
                        "-vf",
                        video_filter,
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
                        "-fs",
                        str(final_limit.max_bytes),
                        str(pending),
                    ],
                    context,
                    output_limit=final_limit,
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
                    raise ValueError(
                        "Rendered frame count or duration differs from the editing decision."
                    )
                await run_media_process(
                    [
                        ffmpeg,
                        "-v",
                        "error",
                        "-xerror",
                        "-nostdin",
                        "-i",
                        str(pending),
                        "-f",
                        "null",
                        "-",
                    ],
                    context,
                )
                for asset in {
                    (resolve_existing(clip.asset.source_path), clip.asset.sha256): clip.asset
                    for clip in plan.clips
                }.values():
                    if await hash_source(asset.source_path, context) != asset.sha256:
                        raise ValueError("Source changed during rendering.")
                if music is not None:
                    await _verify_music(music, context)
                if narration is not None and narration_artifact is not None:
                    verify_narration(narration, narration_artifact)
                context.check_cancelled()
                final = target / "video.mp4"
                pending.rename(final)
                digest = await hash_source(final, context)
                files = {"video.mp4": digest}
                if subtitle_mode != "none":
                    files["subtitles.srt"] = await hash_source(subtitle_path, context)
                if narration_artifact is not None:
                    text_path = target / "narration.txt"
                    with text_path.open("xb") as handle:
                        handle.write(narration_artifact.text_path.read_bytes())
                    files["narration.txt"] = await hash_source(text_path, context)
                    if files["narration.txt"] != narration_artifact.text_sha256:
                        raise ValueError("Narration text changed during rendering.")
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
                    "audioMix": mix.to_json(),
                    "music": None if music is None else music.public(),
                    "mixPolicy": {
                        "version": "creation-audio-mix-v1",
                        "sampleRate": 48000,
                        "channels": 2,
                        "musicClock": "output-from-zero-loop-trim" if music else "none",
                        "ducking": mix.ducking if music else "off",
                        "duckingDetector": "raw-source-rms"
                        if music and mix.ducking == "source-v1"
                        else "none",
                        "compressor": {
                            "threshold": 0.015,
                            "ratio": 12,
                            "attackMs": 10,
                            "releaseMs": 200,
                        }
                        if music and mix.ducking == "source-v1"
                        else None,
                        "normalize": False,
                        "limiter": "0.95-level-false-latency-compensated" if music else "none",
                    },
                    "audioPolicy": "source-clock-resample-or-silence-48000-stereo",
                    "limitations": [
                        "hard cuts and linear crossfades",
                        "letterbox",
                        "no overlays",
                        "burn uses centisecond timing and visible fullwidth ASS control characters",
                    ],
                }
                if any(clip.speed != 1 for clip in plan.clips):
                    result["speedPolicy"] = {
                        "version": "clip-speed-v1",
                        "audio": "source-clock-pad-atempo-pitch-preserving-output-trim",
                        "musicClock": "output-unchanged",
                        "clips": [
                            {
                                "numerator": clip.speed.numerator,
                                "denominator": clip.speed.denominator,
                            }
                            for clip in plan.clips
                        ],
                    }
                # Remove only our deterministic temporary files, after validation, before completion.
                for part in [*parts, *joined_parts]:
                    part.unlink()
                manifest.unlink()
                if ass_path.exists():
                    ass_path.unlink()
                context.check_cancelled()
                if narration is not None and narration_artifact is not None:
                    result["narration"] = narration_receipt(narration, narration_artifact, plan.fps)
                with (target / "receipt.partial.json").open("x", encoding="utf-8") as handle:
                    json.dump(result, handle, ensure_ascii=False, indent=2)
                context.check_cancelled()
                (target / "receipt.partial.json").rename(target / "receipt.json")
                return {"output": str(target), "video": str(final), **result}
            finally:
                for part in joined_parts:
                    part.unlink(missing_ok=True)
        finally:
            # Every name is generated in this exclusive output directory, including
            # a part whose process failed before it could be appended to parts.
            for index in range(len(plan.clips)):
                (target / f"part-{index:06d}.nut").unlink(missing_ok=True)
                if index:
                    (target / f"join-{index:06d}.nut").unlink(missing_ok=True)
            (target / "parts.txt").unlink(missing_ok=True)
            ass_path.unlink(missing_ok=True)
