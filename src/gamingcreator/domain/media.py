from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Literal

from gamingcreator.domain.time import INT64_MAX, SourceInstant, SourceRange


def floor_us(seconds: Fraction) -> int:
    return (seconds * 1_000_000).__floor__()


def ceil_us(seconds: Fraction) -> int:
    return (seconds * 1_000_000).__ceil__()


@dataclass(frozen=True, slots=True)
class MediaStream:
    index: int
    kind: Literal["video", "audio"]
    time_base: Fraction
    start_pts: int
    duration_ts: int

    def __post_init__(self) -> None:
        if self.time_base <= 0 or type(self.start_pts) is not int:
            raise ValueError("Invalid stream clock.")
        if (
            type(self.index) is not int
            or self.index < 0
            or type(self.duration_ts) is not int
            or self.duration_ts <= 0
        ):
            raise ValueError("Invalid stream identity or duration.")

    @property
    def start_seconds(self) -> Fraction:
        return self.start_pts * self.time_base

    @property
    def end_seconds(self) -> Fraction:
        return (self.start_pts + self.duration_ts) * self.time_base


@dataclass(frozen=True, slots=True)
class MediaAsset:
    media_id: str
    source_path: Path
    sha256: str
    streams: tuple[MediaStream, ...]
    origin_seconds: Fraction
    duration_us: int
    probe_version: str

    def __post_init__(self) -> None:
        if not self.streams or not any(s.kind == "video" for s in self.streams):
            raise ValueError("A video stream is required.")
        if self.origin_seconds != min(s.start_seconds for s in self.streams):
            raise ValueError(
                "Origin must preserve the selected streams' common presentation clock."
            )
        expected_duration = ceil_us(max(s.end_seconds for s in self.streams) - self.origin_seconds)
        if (
            type(self.duration_us) is not int
            or not 0 < self.duration_us <= INT64_MAX
            or self.duration_us != expected_duration
        ):
            raise ValueError("Invalid normalized duration.")

    def instant(self, pts: int, time_base: Fraction) -> SourceInstant:
        return SourceInstant(floor_us(pts * time_base - self.origin_seconds), self.duration_us)


@dataclass(frozen=True, slots=True)
class VisualEvidence:
    evidence_id: str
    path: Path
    sha256: str
    pts: int
    time_base: Fraction
    source_time: SourceInstant


@dataclass(frozen=True, slots=True)
class AudioFrameMapping:
    sample_offset: int
    sample_count: int
    pts: int
    time_base: Fraction

    def __post_init__(self) -> None:
        if (
            any(type(v) is not int for v in (self.sample_offset, self.sample_count, self.pts))
            or self.sample_offset < 0
            or self.sample_count <= 0
            or self.time_base <= 0
        ):
            raise ValueError("Invalid audio frame mapping.")


@dataclass(frozen=True, slots=True)
class AudioRangeMapping:
    source_range: SourceRange
    discontinuity_offsets: tuple[int, ...]
    clamped_start_seconds: Fraction
    clamped_end_seconds: Fraction

    @property
    def uncertain(self) -> bool:
        return bool(
            self.discontinuity_offsets or self.clamped_start_seconds or self.clamped_end_seconds
        )


@dataclass(frozen=True, slots=True)
class AudioEvidence:
    evidence_id: str
    path: Path
    sha256: str
    sample_rate: int
    sample_count: int
    frames: tuple[AudioFrameMapping, ...]
    trim_end_pts: int | None = None
    decoded_sample_count: int | None = None

    def __post_init__(self) -> None:
        if type(self.sample_rate) is not int or self.sample_rate <= 0 or not self.frames:
            raise ValueError("Audio needs a sample clock and frame mapping.")
        offset = 0
        previous_pts: Fraction | None = None
        for frame in self.frames:
            clock = frame.pts * frame.time_base
            if frame.sample_offset != offset or frame.time_base != Fraction(1, self.sample_rate):
                raise ValueError("WAV sample mapping is incomplete.")
            if previous_pts is not None and clock <= previous_pts:
                raise ValueError("Audio frame PTS must increase.")
            offset += frame.sample_count
            previous_pts = clock
        if type(self.sample_count) is not int or offset != self.sample_count:
            raise ValueError("WAV sample count differs from decoded mapping.")
        if self.decoded_sample_count is not None and self.decoded_sample_count < self.sample_count:
            raise ValueError("Decoded sample count cannot be less than retained audio.")

    @property
    def discontinuity_offsets(self) -> tuple[int, ...]:
        return tuple(
            current.sample_offset
            for previous, current in zip(self.frames, self.frames[1:], strict=False)
            if current.pts != previous.pts + previous.sample_count
        )

    def map_interval(
        self, start_sample: int, end_sample: int, asset: MediaAsset
    ) -> AudioRangeMapping:
        if (
            type(start_sample) is not int
            or type(end_sample) is not int
            or not 0 <= start_sample < end_sample <= self.sample_count
        ):
            raise ValueError("Audio interval is outside the WAV sample axis.")
        pieces = []
        for frame in self.frames:
            start = max(start_sample, frame.sample_offset)
            end = min(end_sample, frame.sample_offset + frame.sample_count)
            if start < end:
                pieces.append(
                    (
                        (frame.pts + start - frame.sample_offset) * frame.time_base
                        - asset.origin_seconds,
                        (frame.pts + end - frame.sample_offset) * frame.time_base
                        - asset.origin_seconds,
                    )
                )
        start_time, end_time = min(s for s, _ in pieces), max(e for _, e in pieces)
        # Resampler quantization can overshoot container duration by at most one output sample.
        duration = Fraction(asset.duration_us, 1_000_000)
        if start_time < -Fraction(1, self.sample_rate) or end_time > duration + Fraction(
            1, self.sample_rate
        ):
            raise ValueError("Mapped audio exceeds the source clock.")
        source = SourceRange(
            max(floor_us(start_time), 0),
            min(ceil_us(end_time), asset.duration_us),
            asset.duration_us,
        )
        discontinuities = tuple(
            offset for offset in self.discontinuity_offsets if start_sample < offset < end_sample
        )
        return AudioRangeMapping(
            source,
            discontinuities,
            max(-start_time, Fraction(0)),
            max(end_time - duration, Fraction(0)),
        )


@dataclass(frozen=True, slots=True)
class MediaPreprocessingResult:
    asset: MediaAsset
    images: tuple[VisualEvidence, ...]
    audio: AudioEvidence | None
    manifest_path: Path
    transform_version: str
    processor_version: str
