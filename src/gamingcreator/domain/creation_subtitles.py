"""Exact output-clock subtitle cues and strict, local SRT text conversion."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction


def _text(value: str) -> str:
    # Empty lines delimit SRT records; do not allow text to introduce records.
    lines = [line.strip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    result = "\n".join(line for line in lines if line)
    if not result or "-->" in result or "\x00" in result:
        raise ValueError("Subtitle text must be nonempty and cannot contain SRT timing syntax.")
    return result


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    """Half-open seconds on the output clock; uncertainty remains internal."""

    start: Fraction
    end: Fraction
    text: str
    uncertainty: str | None = None
    clip_index: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.start, Fraction) or not isinstance(self.end, Fraction):
            raise ValueError("Subtitle times must be exact Fraction seconds.")
        if not 0 <= self.start < self.end:
            raise ValueError("Subtitle interval must be nonnegative and nonempty.")
        if self.clip_index is not None and (
            type(self.clip_index) is not int or self.clip_index < 0
        ):
            raise ValueError("Subtitle clip identity must be a nonnegative integer.")
        object.__setattr__(self, "text", _text(self.text))


def _timestamp(milliseconds: int) -> str:
    seconds, ms = divmod(milliseconds, 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f"{hours:02d}:{minute:02d}:{sec:02d},{ms:03d}"


def serialize_srt(cues: Iterable[SubtitleCue]) -> str:
    """Floor exact times to milliseconds; omit intervals collapsed by quantization."""
    blocks: list[str] = []
    for cue in sorted(cues, key=lambda cue: (cue.start, cue.end)):
        start = (cue.start * 1000).__floor__()
        end = (cue.end * 1000).__floor__()
        if start == end:
            continue
        blocks.append(f"{len(blocks) + 1}\n{_timestamp(start)} --> {_timestamp(end)}\n{cue.text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


_TIME = r"([0-9]{2,}):([0-9]{2}):([0-9]{2}),([0-9]{3})"
_TIMING = re.compile(rf"{_TIME} --> {_TIME}")


def _seconds(parts: tuple[str, ...]) -> Fraction:
    hours, minutes, seconds, ms = map(int, parts)
    if minutes >= 60 or seconds >= 60:
        raise ValueError("Invalid SRT clock.")
    return Fraction(((hours * 60 + minutes) * 60 + seconds) * 1000 + ms, 1000)


def parse_srt(text: str) -> tuple[SubtitleCue, ...]:
    """Read consecutive numbered SRT records without guessing invalid clocks."""
    normalized = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ()
    cues: list[SubtitleCue] = []
    for block in re.split(r"\n[ \t]*\n", normalized):
        lines = block.split("\n")
        if len(lines) < 3 or lines[0] != str(len(cues) + 1):
            raise ValueError("Invalid SRT record or nonconsecutive numbering.")
        match = _TIMING.fullmatch(lines[1])
        if match is None:
            raise ValueError("Invalid SRT timing line.")
        cues.append(
            SubtitleCue(
                _seconds(match.groups()[:4]), _seconds(match.groups()[4:]), "\n".join(lines[2:])
            )
        )
    return tuple(cues)
