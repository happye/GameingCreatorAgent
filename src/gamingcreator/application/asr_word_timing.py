"""Probe ASR word-level timestamps and map real words onto the edit timeline.

Never invent per-word timings from segment text. Local ASR today stores only
segment ranges; this module documents that gap and maps words only when a
provider payload already carries them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from fractions import Fraction
from typing import Any

from gamingcreator.application.rendering import RenderPlan
from gamingcreator.domain.creation_subtitles import SubtitleCue
from gamingcreator.domain.media import AudioEvidence, AudioRangeMapping, MediaAsset
from gamingcreator.domain.models import TranscriptSegment
from gamingcreator.domain.time import SourceRange


class _InvalidWavSeconds(Exception):
    """Internal: raw worker seconds could not be read as a finite interval."""


def _wav_seconds(seconds: object, rate: int, max_samples: int) -> Decimal:
    if type(seconds) not in (str, int, float):
        raise _InvalidWavSeconds("WAV 时间无法映回源时钟。")
    try:
        value = Decimal(str(seconds))
        if not value.is_finite() or value < 0 or value > Decimal(max_samples) / rate:
            raise _InvalidWavSeconds("WAV 时间无法映回源时钟。")
        return value
    except (ArithmeticError, ValueError):
        raise _InvalidWavSeconds("WAV 时间无法映回源时钟。") from None


@dataclass(frozen=True, slots=True)
class WavSourceInterval:
    start_sample: int
    end_sample: int
    mapping: AudioRangeMapping


def map_wav_seconds_to_source(
    clock: AudioEvidence, asset: MediaAsset, start: object, end: object
) -> WavSourceInterval:
    """Map worker or segment seconds onto the source clock with the official sample rounding."""
    try:
        start_seconds = _wav_seconds(start, clock.sample_rate, clock.sample_count)
        end_seconds = _wav_seconds(end, clock.sample_rate, clock.sample_count)
    except _InvalidWavSeconds as error:
        raise ValueError("WAV 时间无法映回源时钟。") from error
    if start_seconds >= end_seconds:
        raise ValueError("WAV 时间无法映回源时钟。")
    start_sample = int((start_seconds * clock.sample_rate).to_integral_value(rounding=ROUND_FLOOR))
    end_sample = int((end_seconds * clock.sample_rate).to_integral_value(rounding=ROUND_CEILING))
    if start_sample < 0 or end_sample > clock.sample_count:
        raise ValueError("WAV 时间无法映回源时钟。")
    try:
        mapping = clock.map_interval(start_sample, end_sample, asset)
    except ValueError as error:
        raise ValueError("WAV 时间无法映回源时钟。") from error
    return WavSourceInterval(start_sample, end_sample, mapping)


PROBE_VERSION = "asr-word-timing-probe-v1"
WORD_UNCERTAINTY = "asr-word"


@dataclass(frozen=True, slots=True)
class WorkerWord:
    """One word as the local worker reported it: original text and start/end strings."""

    text: str
    start: str
    end: str


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


def collect_worker_words(result: Mapping[str, Any]) -> tuple[WorkerWord, ...]:
    """Collect only the worker's own word rows. Missing or empty words yield an empty set.

    Segment text is never split by punctuation, character count, or equal duration.
    """
    if not isinstance(result, Mapping):
        raise ValueError("Worker result must be an object.")
    raw = result.get("words")
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("Worker words must be a list when present.")
    words: list[WorkerWord] = []
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != {"start", "end", "text"}:
            raise ValueError("Each worker word must have start, end, and text.")
        text = item["text"]
        start = item["start"]
        end = item["end"]
        if not isinstance(text, str) or not isinstance(start, str) or not isinstance(end, str):
            raise ValueError("Worker word text, start, and end must be strings.")
        words.append(WorkerWord(text, start, end))
    return tuple(words)


def validate_worker_words(
    words: Sequence[WorkerWord],
    *,
    sample_rate: int,
    sample_count: int,
) -> tuple[WorkerWord, ...]:
    """Reject non-finite, reversed, zero-length, or out-of-range times. Never rewrite them."""
    if (
        type(sample_rate) is not int
        or sample_rate <= 0
        or type(sample_count) is not int
        or sample_count <= 0
    ):
        raise ValueError("音频时钟无效。")
    if not isinstance(words, Sequence) or isinstance(words, (str, bytes)):
        raise ValueError("词记录必须是列表。")
    duration = Decimal(sample_count) / sample_rate
    for word in words:
        start = _word_seconds(word.start, duration)
        end = _word_seconds(word.end, duration)
        if start >= end:
            raise ValueError("词时间无效：存在倒序、零长或无法使用的时间。")
    return tuple(words)


def _word_seconds(value: str, duration: Decimal) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("词时间无效：存在非有限、倒序、零长或超出音频范围的记录。")
    try:
        seconds = Decimal(value)
    except (ArithmeticError, ValueError):
        raise ValueError("词时间无效：存在非有限、倒序、零长或超出音频范围的记录。") from None
    if not seconds.is_finite() or seconds < 0 or seconds > duration:
        raise ValueError("词时间无效：存在非有限、倒序、零长或超出音频范围的记录。")
    return seconds


def map_worker_words_to_source(
    words: Sequence[WorkerWord],
    clock: AudioEvidence,
    asset: MediaAsset,
) -> tuple[AsrWord, ...]:
    """Map validated worker seconds through the official WAV sample rounding and source clock."""
    mapped: list[AsrWord] = []
    for word in words:
        interval = map_wav_seconds_to_source(clock, asset, word.start, word.end)
        mapped.append(AsrWord(asset.media_id, interval.mapping.source_range, word.text))
    return tuple(mapped)


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


def stitch_window_words(windows: Sequence[Sequence[AsrWord]]) -> tuple[AsrWord, ...]:
    """Keep word identity and source-time order across overlapping windows.

    Same-source overlapping repeats of the same text are kept once, with the
    original times of the earliest row. Words from different sources stay
    separate and are never concatenated.
    """
    flattened: list[AsrWord] = []
    for window in windows:
        flattened.extend(window)
    flattened.sort(
        key=lambda word: (
            word.source_range.start_us,
            word.source_range.end_us,
            word.media_id,
            word.text,
        )
    )
    kept: list[AsrWord] = []
    for word in flattened:
        if any(
            existing.media_id == word.media_id
            and existing.text == word.text
            and _source_ranges_overlap(existing.source_range, word.source_range)
            for existing in kept
        ):
            continue
        kept.append(word)
    return tuple(kept)


def _source_ranges_overlap(left: SourceRange, right: SourceRange) -> bool:
    return left.start_us < right.end_us and right.start_us < left.end_us


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
