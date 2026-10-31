"""Map saved ASR source intervals onto the ordered render output clock."""

from collections.abc import Iterable
from fractions import Fraction

from gamingcreator.application.rendering import RenderPlan
from gamingcreator.domain.creation_subtitles import SubtitleCue
from gamingcreator.domain.models import TranscriptSegment


def build_subtitles(
    plan: RenderPlan,
    transcripts: Iterable[TranscriptSegment],
    *,
    per_clip: Iterable[Iterable[TranscriptSegment]] | None = None,
    overrides: Iterable[str | None] | None = None,
) -> tuple[SubtitleCue, ...]:
    """Intersect same-media source speech, preserving each occurrence in the edit."""
    if type(plan.fps) is not int or plan.fps <= 0:
        raise ValueError("Output frame rate must be a positive integer.")
    segments = tuple(transcripts)
    clip_segments = None if per_clip is None else tuple(tuple(items) for items in per_clip)
    texts = (None,) * len(plan.clips) if overrides is None else tuple(overrides)
    if len(texts) != len(plan.clips):
        raise ValueError("Subtitle overrides must match render clips.")
    for text in texts:
        if text is not None:
            validate_override_text(text)
    if clip_segments is not None and len(clip_segments) != len(plan.clips):
        raise ValueError("Subtitle transcript groups must match render clips.")
    cues: list[SubtitleCue] = []
    output_frame = 0
    for index, clip in enumerate(plan.clips):
        if type(clip.output_frames) is not int or clip.output_frames <= 0:
            raise ValueError("Output clips need a positive integer frame count.")
        offset = Fraction(output_frame, plan.fps)
        duration = Fraction(clip.output_frames, plan.fps)
        text = texts[index]
        if text is not None:
            if text != "":
                cues.append(SubtitleCue(offset, offset + duration, text, "user-written"))
            output_frame += clip.output_frames
            continue
        clip_cues: list[SubtitleCue] = []
        for segment in segments if clip_segments is None else clip_segments[index]:
            if segment.media_id != clip.asset.media_id or not segment.text.strip():
                continue
            start_us = max(clip.source_range.start_us, segment.source_range.start_us)
            end_us = min(clip.source_range.end_us, segment.source_range.end_us)
            if start_us >= end_us:
                continue
            start = Fraction(start_us - clip.source_range.start_us, 1_000_000) / clip.speed
            end = min(
                Fraction(end_us - clip.source_range.start_us, 1_000_000) / clip.speed, duration
            )
            if start < end:
                clip_cues.append(
                    SubtitleCue(offset + start, offset + end, segment.text, segment.uncertainty)
                )
        cues.extend(sorted(clip_cues, key=lambda cue: (cue.start, cue.end)))
        output_frame += clip.output_frames
    return tuple(cues)


def validate_override_text(text: str) -> None:
    """Prevalidate a user's text without turning it into source ASR evidence."""
    if not isinstance(text, str) or len(text) > 2000:
        raise ValueError("Subtitle override text must be a string of at most 2000 characters.")
    if any(ord(c) < 32 and c not in "\r\n\t" or ord(c) == 127 for c in text):
        raise ValueError("Subtitle override text contains control characters.")
    if text:
        SubtitleCue(Fraction(0), Fraction(1), text, "user-written")
