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


@dataclass(frozen=True, slots=True)
class AudioMix:
    bgm: BgmSelection | None = None
    source_gain_db: float = 0.0
    ducking: str = "off"

    def __post_init__(self) -> None:
        if self.bgm is not None and not isinstance(self.bgm, BgmSelection):
            raise ValueError("Invalid BGM selection.")
        object.__setattr__(self, "source_gain_db", _gain(self.source_gain_db))
        if self.ducking not in ("off", "source-v1"):
            raise ValueError("Unsupported audio ducking policy.")

    @classmethod
    def from_json(cls, value: object) -> "AudioMix":
        if not isinstance(value, dict) or set(value) != {"bgm", "sourceGainDb", "ducking"}:
            raise ValueError("Invalid audio mix fields.")
        bgm = value["bgm"]
        selection = None
        if bgm is not None:
            if not isinstance(bgm, dict) or set(bgm) != {"trackId", "trackReceiptSha256", "gainDb"}:
                raise ValueError("Invalid BGM fields.")
            selection = BgmSelection(
                bgm["trackId"], bgm["trackReceiptSha256"], _gain(bgm["gainDb"])
            )
        return cls(selection, _gain(value["sourceGainDb"]), value["ducking"])

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
        }
