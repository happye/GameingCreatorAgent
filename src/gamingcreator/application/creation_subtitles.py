"""Map saved ASR source intervals onto the ordered render output clock."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from gamingcreator.application.ad_cut import AD_ACTIONS
from gamingcreator.application.narration import NarrationArtifact
from gamingcreator.application.rendering import RenderPlan
from gamingcreator.application.showcase_topics import retained_source_topics
from gamingcreator.domain.creation_narration import NarrationSelection
from gamingcreator.domain.creation_subtitles import SubtitleCue
from gamingcreator.domain.models import TranscriptSegment


def ad_caption_fallback(
    plan: RenderPlan, edit: dict[str, Any], cues: tuple[SubtitleCue, ...]
) -> tuple[SubtitleCue, ...]:
    """For a silent ad, label retained selling points and the selected call to action."""
    action = AD_ACTIONS.get(edit["selectedPlan"])
    if cues or not action:
        return cues
    starts = plan.start_frames
    action_start = max(starts[-1], plan.frames - 2 * plan.fps)
    labels = []
    for index, (row, start) in enumerate(zip(edit["segments"], starts, strict=True)):
        topics = retained_source_topics(row)[:2]
        text = "、".join(topics).replace("-->", "→").replace("\x00", "").strip()[:80]
        next_start = starts[index + 1] if index + 1 < len(starts) else plan.frames
        end = min(next_start, action_start, start + 2 * plan.fps)
        if text and start < end:
            labels.append(SubtitleCue(Fraction(start, plan.fps), Fraction(end, plan.fps), text))
    return (
        *labels,
        SubtitleCue(Fraction(action_start, plan.fps), Fraction(plan.frames, plan.fps), action),
    )


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
    for index, clip in enumerate(plan.clips):
        if type(clip.output_frames) is not int or clip.output_frames <= 0:
            raise ValueError("Output clips need a positive integer frame count.")
        offset = Fraction(plan.start_frames[index], plan.fps)
        duration = Fraction(clip.output_frames, plan.fps)
        text = texts[index]
        if text is not None:
            if text != "":
                cues.append(SubtitleCue(offset, offset + duration, text, "user-written", index))
            continue
        clip_cues: list[SubtitleCue] = []
        for segment in segments if clip_segments is None else clip_segments[index]:
            if segment.media_id != clip.asset.media_id:
                continue
            spoken = segment.text.replace("-->", "→").replace("\x00", "")
            if not spoken.strip():
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
                    SubtitleCue(offset + start, offset + end, spoken, segment.uncertainty, index)
                )
        cues.extend(sorted(clip_cues, key=lambda cue: (cue.start, cue.end)))
    return tuple(sorted(cues, key=lambda cue: (cue.start, cue.end)))


def build_narration_subtitles(
    plan: RenderPlan, selection: NarrationSelection, artifact: NarrationArtifact
) -> tuple[SubtitleCue, ...]:
    """Project measured WAV sample intervals onto the independently positioned audio track."""
    origin = Fraction(selection.start_frame, plan.fps)
    limit = Fraction(plan.frames, plan.fps)
    cues = []
    for span in artifact.caption_spans:
        start = origin + Fraction(span.start_sample, artifact.sample_rate)
        end = min(limit, origin + Fraction(span.end_sample, artifact.sample_rate))
        if start < end and span.text.strip():
            cues.append(SubtitleCue(start, end, span.text.replace("-->", "→"), "narration"))
    return tuple(cues)


def subtitle_layout(
    cues: tuple[SubtitleCue, ...], clock_scale: int
) -> Iterator[tuple[Fraction, Fraction, SubtitleCue, int]]:
    """Stack active tracks, keeping the narration below source clips at overlaps."""
    for cue in cues:
        others = [
            other
            for other in cues
            if other.clip_index != cue.clip_index
            and other.start < cue.end
            and cue.start < other.end
        ]
        edges = {cue.start, cue.end}
        for other in others:
            edges.update((max(cue.start, other.start), min(cue.end, other.end)))
        boundaries = sorted(edges)
        for start, end in zip(boundaries, boundaries[1:], strict=False):
            if int(start * clock_scale) == int(end * clock_scale):
                continue
            higher = {
                other.clip_index
                for other in others
                if other.start < end
                and start < other.end
                and cue.clip_index is not None
                and (other.clip_index is None or cue.clip_index < other.clip_index)
            }
            yield start, end, cue, len(higher)


def validate_override_text(text: str) -> None:
    """Prevalidate a user's text without turning it into source ASR evidence."""
    if not isinstance(text, str) or len(text) > 2000:
        raise ValueError("Subtitle override text must be a string of at most 2000 characters.")
    if any(ord(c) < 32 and c not in "\r\n\t" or ord(c) == 127 for c in text):
        raise ValueError("Subtitle override text contains control characters.")
    if text:
        SubtitleCue(Fraction(0), Fraction(1), text, "user-written")


@dataclass(frozen=True, slots=True)
class SubtitlePresentation:
    cues: tuple[SubtitleCue, ...]
    source: str
    word_highlights: bool


def present_subtitles(
    segment_cues: Iterable[SubtitleCue],
    words: Iterable[object] | None = None,
    *,
    sidecar_available: bool = False,
    plan: RenderPlan | None = None,
    per_clip: Iterable[Iterable[object]] | None = None,
    reserved_clip_indexes: Iterable[int] | None = None,
) -> SubtitlePresentation:
    """只有核对过的词级结果才进入已有剪辑映射；手写或留空的镜头保持原样。"""
    cues = tuple(segment_cues)
    fallback = SubtitlePresentation(cues=cues, source="segment", word_highlights=False)
    if not sidecar_available or words is None or plan is None:
        return fallback
    word_list = tuple(words)
    if not word_list:
        return fallback
    from gamingcreator.application.asr_word_timing import AsrWord, map_words_to_edit_timeline

    if any(type(word) is not AsrWord for word in word_list):
        return fallback
    typed_words = tuple(word for word in word_list if type(word) is AsrWord)
    typed_clips = (
        None
        if per_clip is None
        else tuple(tuple(word for word in clip if type(word) is AsrWord) for clip in per_clip)
    )
    mapped = map_words_to_edit_timeline(plan, typed_words, per_clip=typed_clips)
    reserved = {index for index in (reserved_clip_indexes or ()) if type(index) is int}
    reserved |= {
        cue.clip_index
        for cue in cues
        if cue.uncertainty == "user-written" and type(cue.clip_index) is int
    }
    word_cues = tuple(cue for cue in mapped if cue.clip_index not in reserved)
    if not word_cues:
        return fallback
    used = {cue.clip_index for cue in word_cues}
    kept = tuple(cue for cue in cues if cue.clip_index in reserved or cue.clip_index not in used)
    combined = tuple(sorted((*kept, *word_cues), key=lambda cue: (cue.start, cue.end)))
    return SubtitlePresentation(cues=combined, source="words", word_highlights=True)


def export_subtitle_tracks(
    segment_cues: Iterable[SubtitleCue],
    words: Iterable[object] | None = None,
    *,
    sidecar_available: bool = False,
    plan: RenderPlan | None = None,
    per_clip: Iterable[Iterable[object]] | None = None,
    reserved_clip_indexes: Iterable[int] | None = None,
) -> tuple[tuple[SubtitleCue, ...], tuple[SubtitleCue, ...] | None]:
    """SRT 始终用段级字幕；只有核对过的词级结果才进入烧录。"""
    sidecar = present_subtitles(segment_cues)
    burned = present_subtitles(
        segment_cues,
        words,
        sidecar_available=sidecar_available,
        plan=plan,
        per_clip=per_clip,
        reserved_clip_indexes=reserved_clip_indexes,
    )
    return sidecar.cues, (burned.cues if burned.word_highlights else None)
