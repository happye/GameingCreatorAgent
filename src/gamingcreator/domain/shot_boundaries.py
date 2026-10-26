"""Shot boundaries and black intervals from per-frame scene-change evidence.

Pure computation: no I/O. Inputs are frame instants already mapped to the source clock
(microseconds from the media origin). The rules are local heuristics; their accuracy on
real gameplay has not been judged by a human.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from gamingcreator.domain.time import SourceRange


@dataclass(frozen=True, slots=True)
class CutCandidate:
    """A frame whose scene-change score passed the detector threshold (first frame after)."""

    time_us: int
    score: float


@dataclass(frozen=True, slots=True)
class BlackTransition:
    """First black frame (``starts_black``) or first frame after black."""

    time_us: int
    starts_black: bool


@dataclass(frozen=True, slots=True)
class ShotParameters:
    min_shot_us: int = 500_000
    flash_us: int = 120_000
    min_black_us: int = 200_000

    def __post_init__(self) -> None:
        values = (self.min_shot_us, self.flash_us, self.min_black_us)
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("Shot parameters must be non-negative integer microseconds.")


@dataclass(frozen=True, slots=True)
class ShotBoundaries:
    cuts: tuple[CutCandidate, ...]
    black: tuple[SourceRange, ...]
    shots: tuple[SourceRange, ...]
    flashes_dropped: int
    close_cuts_dropped: int


@dataclass(frozen=True, slots=True)
class SpanReport:
    cuts_inside: int
    black_overlap_us: int
    shots_touched: int


def black_intervals(
    transitions: Sequence[BlackTransition], duration_us: int, min_black_us: int
) -> tuple[SourceRange, ...]:
    """Pair black start/end transitions; an unterminated black run lasts to the end."""
    intervals: list[SourceRange] = []
    start: int | None = None
    for item in sorted(transitions, key=lambda value: (value.time_us, not value.starts_black)):
        if not 0 <= item.time_us <= duration_us:
            continue
        if item.starts_black:
            if start is None:
                start = item.time_us
        elif start is not None:
            if item.time_us - start >= min_black_us and item.time_us > start:
                intervals.append(SourceRange(start, item.time_us, duration_us))
            start = None
    if start is not None and duration_us - start >= min_black_us and duration_us > start:
        intervals.append(SourceRange(start, duration_us, duration_us))
    return tuple(intervals)


def _inside(time_us: int, ranges: Sequence[SourceRange]) -> bool:
    return any(item.start_us <= time_us <= item.end_us for item in ranges)


def frames_span_cut(first_us: int, last_us: int, boundaries: ShotBoundaries) -> int:
    """Accepted cuts between two frame instants: the later frame shows a different shot."""
    return sum(1 for item in boundaries.cuts if first_us < item.time_us <= last_us)


def detect_shot_boundaries(
    candidates: Sequence[CutCandidate],
    transitions: Sequence[BlackTransition],
    duration_us: int,
    parameters: ShotParameters | None = None,
) -> ShotBoundaries:
    """Accepted cuts, black intervals and the non-black shots between boundaries.

    Two candidates closer than ``flash_us`` are a flash (into and out of one bright or
    dark frame) and both are dropped. A later candidate closer than ``min_shot_us`` to the
    previous accepted cut is dropped. Candidates on or inside black intervals are covered by
    the black boundaries themselves.
    """
    settings = parameters or ShotParameters()
    if type(duration_us) is not int or duration_us <= 0:
        raise ValueError("Media duration must be a positive integer.")
    black = black_intervals(transitions, duration_us, settings.min_black_us)
    ordered = sorted(
        (item for item in candidates if 0 < item.time_us < duration_us),
        key=lambda item: item.time_us,
    )
    flashes: set[int] = set()
    for index in range(len(ordered) - 1):
        if ordered[index + 1].time_us - ordered[index].time_us < settings.flash_us:
            flashes.update((index, index + 1))
    accepted: list[CutCandidate] = []
    close = 0
    for index, item in enumerate(ordered):
        if index in flashes or _inside(item.time_us, black):
            continue
        if accepted and item.time_us - accepted[-1].time_us < settings.min_shot_us:
            close += 1
            continue
        accepted.append(item)
    boundaries = sorted(
        {item.time_us for item in accepted}
        | {edge for item in black for edge in (item.start_us, item.end_us)}
        | {0, duration_us}
    )
    shots = tuple(
        SourceRange(start, end, duration_us)
        for start, end in zip(boundaries, boundaries[1:], strict=False)
        if end > start and not any(item.start_us <= start and end <= item.end_us for item in black)
    )
    return ShotBoundaries(tuple(accepted), black, shots, len(flashes), close)


# Event edges and frame instants are rounded to whole microseconds on different sides; a
# cut this close to an edge starts or ends the range rather than falling inside it.
EDGE_TOLERANCE_US = 1_000


def span_report(source_range: SourceRange, boundaries: ShotBoundaries) -> SpanReport:
    """How many accepted cuts fall strictly inside a range, and its black overlap."""
    start, end = source_range.start_us, source_range.end_us
    cuts = sum(
        1
        for item in boundaries.cuts
        if start + EDGE_TOLERANCE_US < item.time_us < end - EDGE_TOLERANCE_US
    )
    black = sum(
        max(0, min(end, item.end_us) - max(start, item.start_us)) for item in boundaries.black
    )
    touched = sum(1 for item in boundaries.shots if item.start_us < end and start < item.end_us)
    return SpanReport(cuts, black, touched)
