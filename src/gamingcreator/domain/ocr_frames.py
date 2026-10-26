"""On-screen text read from video frames: parsing, normalization and recurring texts.

Pure computation: no I/O. Readings come from a local OCR engine; nothing here guesses text
the engine did not return, and accuracy on game footage has not been judged by a human.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_CJK = r"㐀-䶿一-鿿豈-﫿"
# The Chinese recognizer returns one word per character; spaces between two CJK characters
# are layout, not content.
_CJK_GAP = re.compile(rf"(?<=[{_CJK}])\s+(?=[{_CJK}])")
_CJK_CHARACTER = re.compile(rf"[{_CJK}]")
_LATIN_RUN = re.compile(r"[A-Za-z0-9]{3,}")


@dataclass(frozen=True, slots=True)
class OcrWord:
    text: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class OcrLine:
    text: str
    words: tuple[OcrWord, ...]


@dataclass(frozen=True, slots=True)
class OcrReading:
    """One language's reading of one frame (``index`` into the request order)."""

    index: int
    language: str
    width: int
    height: int
    lines: tuple[OcrLine, ...]


@dataclass(frozen=True, slots=True)
class TextSpan:
    text: str
    first_us: int
    last_us: int
    frames: int


def normalize_text(text: str) -> str:
    """Collapse whitespace and drop layout spaces between CJK characters."""
    return _CJK_GAP.sub("", " ".join(text.split()))


def likely_text(text: str) -> bool:
    """At least two CJK characters, or a run of three letters/digits that is not one
    repeated character ("ooo" and "0000" are typical misreads of icons); else noise-like."""
    return len(_CJK_CHARACTER.findall(text)) >= 2 or any(
        len(set(run.lower())) >= 2 for run in _LATIN_RUN.findall(text)
    )


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("OCR record field must be an integer.")
    return value


def _string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("OCR record field must be text.")
    return value


def _items(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ValueError("OCR record field must be a list of objects.")
    return value


def parse_reading(record: Mapping[str, object]) -> OcrReading:
    """Validate one engine frame record; raises ValueError on any malformed field."""
    lines = tuple(
        OcrLine(
            _string(line.get("text")),
            tuple(
                OcrWord(
                    _string(word.get("text")),
                    _integer(word.get("x")),
                    _integer(word.get("y")),
                    _integer(word.get("width")),
                    _integer(word.get("height")),
                )
                for word in _items(line.get("words"))
            ),
        )
        for line in _items(record.get("lines"))
    )
    reading = OcrReading(
        _integer(record.get("index")),
        _string(record.get("language")),
        _integer(record.get("width")),
        _integer(record.get("height")),
        lines,
    )
    if reading.index < 0 or reading.width <= 0 or reading.height <= 0:
        raise ValueError("OCR record has an invalid index or image size.")
    return reading


def recurring_texts(
    readings: Sequence[tuple[int, str]], *, limit: int = 30
) -> tuple[TextSpan, ...]:
    """Most frequent likely texts with their first and last frame instants.

    ``readings`` are (source microseconds, normalized line text). A text counts once per
    frame instant even when several languages or lines repeat it.
    """
    seen: dict[str, set[int]] = {}
    for time_us, text in readings:
        if text and likely_text(text):
            seen.setdefault(text, set()).add(time_us)
    ranked = sorted(seen.items(), key=lambda item: (-len(item[1]), min(item[1]), item[0]))
    return tuple(
        TextSpan(text, min(times), max(times), len(times)) for text, times in ranked[:limit]
    )
