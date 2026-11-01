"""Probe ASR word-level timestamps and map real words onto the edit timeline.

Never invent per-word timings from segment text. Local ASR today stores only
segment ranges; this module documents that gap and maps words only when a
provider payload already carries them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from gamingcreator.application.rendering import RenderPlan
from gamingcreator.domain.creation_subtitles import SubtitleCue
from gamingcreator.domain.models import TranscriptSegment
from gamingcreator.domain.time import SourceRange

PROBE_VERSION = "asr-word-timing-probe-v1"
WORD_UNCERTAINTY = "asr-word"


@dataclass(frozen=True, slots=True)
class AsrWord:
    media_id: str
    source_range: SourceRange
    text: str


@dataclass(frozen=True, slots=True)
class WordTimingProbeResult:
    version: str
    available: bool
    gap: str | None
    evidence: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "available": self.available,
            "gap": self.gap,
            "evidence": list(self.evidence),
        }


def probe_local_asr_word_timing() -> WordTimingProbeResult:
    """Inspect the pinned local ASR contract without running the model."""
    evidence = (
        "asr_worker.transcribe rows are {start,end,text} only; word_timestamps not enabled",
        "TranscriptSegment fields are media_id/source_range/text/uncertainty (no words)",
        "sqlite transcript_segments stores segment text ranges only",
        "build_subtitles maps segment intervals, not per-word clocks",
    )
    return WordTimingProbeResult(
        PROBE_VERSION,
        False,
        (
            "Local faster-whisper worker and transcript store do not persist word-level "
            "timestamps; enable a contract change before mapping words. Do not invent timings."
        ),
        evidence,
    )


def transcript_segment_has_words(segment: TranscriptSegment) -> bool:
    """Current domain segments never carry words; keep the check explicit for callers."""
    return hasattr(segment, "words") and bool(segment.words)


def words_from_provider_segment(
    media_id: str,
    duration_us: int,
    payload: Mapping[str, Any],
) -> tuple[AsrWord, ...]:
    """Extract words only from an explicit provider words list. Never split text."""
    if type(duration_us) is not int or duration_us <= 0:
        raise ValueError("duration_us must be a positive integer.")
    if not isinstance(media_id, str) or not media_id:
        raise ValueError("media_id is required.")
    raw = payload.get("words")
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("words must be a list when present.")
    words: list[AsrWord] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("Each word must be an object.")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Word text must be a nonempty string.")
        start_us, end_us = _word_bounds_us(item)
        words.append(AsrWord(media_id, SourceRange(start_us, end_us, duration_us), text.strip()))
    return tuple(words)


def _word_bounds_us(item: Mapping[str, Any]) -> tuple[int, int]:
    if "startUs" in item or "endUs" in item:
        start = item.get("startUs")
        end = item.get("endUs")
        if type(start) is not int or type(end) is not int:
            raise ValueError("Word startUs/endUs must be integers.")
        return start, end
    start = item.get("start")
    end = item.get("end")
    if type(start) not in (int, float) or type(end) not in (int, float):
        raise ValueError("Word start/end seconds are required when startUs/endUs are absent.")
    assert isinstance(start, (int, float)) and isinstance(end, (int, float))
    start_us = int(round(float(start) * 1_000_000))
    end_us = int(round(float(end) * 1_000_000))
    return start_us, end_us


def map_words_to_edit_timeline(
    plan: RenderPlan,
    words: Iterable[AsrWord],
    *,
    per_clip: Iterable[Iterable[AsrWord]] | None = None,
) -> tuple[SubtitleCue, ...]:
    """Map provider words onto the ordered render output clock (same rules as segments)."""
    if type(plan.fps) is not int or plan.fps <= 0:
        raise ValueError("Output frame rate must be a positive integer.")
    all_words = tuple(words)
    clip_words = None if per_clip is None else tuple(tuple(items) for items in per_clip)
    if clip_words is not None and len(clip_words) != len(plan.clips):
        raise ValueError("Word groups must match render clips.")
    cues: list[SubtitleCue] = []
    for index, clip in enumerate(plan.clips):
        if type(clip.output_frames) is not int or clip.output_frames <= 0:
            raise ValueError("Output clips need a positive integer frame count.")
        offset = Fraction(plan.start_frames[index], plan.fps)
        duration = Fraction(clip.output_frames, plan.fps)
        clip_cues: list[SubtitleCue] = []
        for word in all_words if clip_words is None else clip_words[index]:
            if word.media_id != clip.asset.media_id or not word.text.strip():
                continue
            start_us = max(clip.source_range.start_us, word.source_range.start_us)
            end_us = min(clip.source_range.end_us, word.source_range.end_us)
            if start_us >= end_us:
                continue
            start = Fraction(start_us - clip.source_range.start_us, 1_000_000) / clip.speed
            end = min(
                Fraction(end_us - clip.source_range.start_us, 1_000_000) / clip.speed, duration
            )
            if start < end:
                clip_cues.append(
                    SubtitleCue(offset + start, offset + end, word.text, WORD_UNCERTAINTY, index)
                )
        cues.extend(sorted(clip_cues, key=lambda cue: (cue.start, cue.end)))
    return tuple(sorted(cues, key=lambda cue: (cue.start, cue.end)))
