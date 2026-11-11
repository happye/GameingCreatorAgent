"""Strict, immutable local soundtrack selections and output gain settings."""

import re
from dataclasses import dataclass
from math import isfinite
from typing import Any, cast


def _gain(value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError("Audio gain must be a number.")
    number = cast(int | float, value)
    if not -60 <= number <= 0 or not isfinite(number):
        raise ValueError("Audio gain must be finite between -60 and 0 dB.")
    return float(number)


def _hex(value: object, length: int) -> str:
    if not isinstance(value, str) or re.fullmatch(f"[0-9a-f]{{{length}}}", value) is None:
        raise ValueError("Invalid music identity.")
    return value


@dataclass(frozen=True, slots=True)
class BgmSelection:
    track_id: str
    track_receipt_sha256: str
    gain_db: float

    def __post_init__(self) -> None:
        _hex(self.track_id, 32)
        _hex(self.track_receipt_sha256, 64)
        object.__setattr__(self, "gain_db", _gain(self.gain_db))


ENVELOPE_POINTS = 64


@dataclass(frozen=True, slots=True)
class GainPoint:
    """One source-volume keyframe: output frame and gain offset in dB (stage C, 2026-11-11)."""

    frame: int
    gain_db: float

    def __post_init__(self) -> None:
        if type(self.frame) is not int or self.frame < 0:
            raise ValueError("Keyframe frame must be a non-negative integer.")
        object.__setattr__(self, "gain_db", _gain(self.gain_db))


def _envelope(value: object) -> tuple[GainPoint, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= ENVELOPE_POINTS:
        raise ValueError(f"Source envelope needs 1 to {ENVELOPE_POINTS} points.")
    points = []
    for row in value:
        if not isinstance(row, dict) or set(row) != {"frame", "gainDb"}:
            raise ValueError("Invalid source envelope point.")
        points.append(GainPoint(row["frame"], row["gainDb"]))
    if any(b.frame <= a.frame for a, b in zip(points, points[1:], strict=False)):
        raise ValueError("Source envelope frames must strictly increase.")
    return tuple(points)


def envelope_db(points: tuple[GainPoint, ...], frame: float) -> float:
    """Gain offset at an output frame: linear in dB between points, held at the ends."""
    if not points:
        return 0.0
    if frame <= points[0].frame:
        return points[0].gain_db
    for a, b in zip(points, points[1:], strict=False):
        if frame <= b.frame:
            return a.gain_db + (b.gain_db - a.gain_db) * (frame - a.frame) / (b.frame - a.frame)
    return points[-1].gain_db


def envelope_expression(points: tuple[GainPoint, ...], fps: int) -> str:
    """The same curve as an FFmpeg expression of output time ``t`` in dB."""

    def seconds(point: GainPoint) -> str:
        return f"{point.frame / fps:.6f}"

    expression = f"{points[-1].gain_db:.4f}"
    for a, b in reversed(list(zip(points, points[1:], strict=False))):
        slope = (b.gain_db - a.gain_db) / ((b.frame - a.frame) / fps)
        segment = f"({a.gain_db:.4f}+({slope:.6f})*(t-{seconds(a)}))"
        expression = f"if(lt(t,{seconds(b)}),{segment},{expression})"
    return f"if(lt(t,{seconds(points[0])}),{points[0].gain_db:.4f},{expression})"


@dataclass(frozen=True, slots=True)
class AudioMix:
    bgm: BgmSelection | None = None
    source_gain_db: float = 0.0
    ducking: str = "off"
    source_envelope: tuple[GainPoint, ...] = ()

    def __post_init__(self) -> None:
        if self.bgm is not None and not isinstance(self.bgm, BgmSelection):
            raise ValueError("Invalid BGM selection.")
        object.__setattr__(self, "source_gain_db", _gain(self.source_gain_db))
        if self.ducking not in ("off", "source-v1"):
            raise ValueError("Unsupported audio ducking policy.")
        if not isinstance(self.source_envelope, tuple) or not all(
            isinstance(p, GainPoint) for p in self.source_envelope
        ):
            raise ValueError("Invalid source envelope.")

    @classmethod
    def from_json(cls, value: object) -> "AudioMix":
        base = {"bgm", "sourceGainDb", "ducking"}
        if not isinstance(value, dict) or set(value) not in (base, base | {"sourceEnvelope"}):
            raise ValueError("Invalid audio mix fields.")
        bgm = value["bgm"]
        selection = None
        if bgm is not None:
            if not isinstance(bgm, dict) or set(bgm) != {"trackId", "trackReceiptSha256", "gainDb"}:
                raise ValueError("Invalid BGM fields.")
            selection = BgmSelection(
                bgm["trackId"], bgm["trackReceiptSha256"], _gain(bgm["gainDb"])
            )
        envelope = _envelope(value["sourceEnvelope"]) if "sourceEnvelope" in value else ()
        return cls(selection, _gain(value["sourceGainDb"]), value["ducking"], envelope)

    def to_json(self) -> dict[str, Any]:
        return {
            "bgm": None
            if self.bgm is None
            else {
                "trackId": self.bgm.track_id,
                "trackReceiptSha256": self.bgm.track_receipt_sha256,
                "gainDb": self.bgm.gain_db,
            },
            "sourceGainDb": self.source_gain_db,
            "ducking": self.ducking,
            # Absent when empty, so versions saved before keyframes keep identical JSON.
            **(
                {
                    "sourceEnvelope": [
                        {"frame": p.frame, "gainDb": p.gain_db} for p in self.source_envelope
                    ]
                }
                if self.source_envelope
                else {}
            ),
        }
