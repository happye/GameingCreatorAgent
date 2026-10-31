"""One immutable narration asset placed on the output frame clock."""

import math
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NarrationSelection:
    asset_job_id: str
    receipt_sha256: str
    start_frame: int
    gain_db: float
    ducking: str

    @classmethod
    def from_json(cls, value: object) -> "NarrationSelection":
        if not isinstance(value, dict) or set(value) != {
            "assetJobId",
            "receiptSha256",
            "startFrame",
            "gainDb",
            "ducking",
        }:
            raise ValueError("Narration requires exact asset, placement and mix fields.")
        asset, digest, start, gain, duck = (
            value[k] for k in ("assetJobId", "receiptSha256", "startFrame", "gainDb", "ducking")
        )
        if not isinstance(asset, str) or re.fullmatch(r"[0-9a-f]{32}", asset) is None:
            raise ValueError("Invalid narration job identity.")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("Invalid narration receipt digest.")
        if type(start) is not int or start < 0:
            raise ValueError("Narration start must be a nonnegative output frame.")
        if type(gain) not in (int, float) or not math.isfinite(gain) or not -60 <= gain <= 0:
            raise ValueError("Narration gain must be finite and within -60 to 0 dB.")
        if not isinstance(duck, str) or duck not in ("off", "narration-v1"):
            raise ValueError("Unsupported narration ducking mode.")
        return cls(asset, digest, start, float(gain), duck)

    def to_json(self) -> dict[str, Any]:
        return {
            "assetJobId": self.asset_job_id,
            "receiptSha256": self.receipt_sha256,
            "startFrame": self.start_frame,
            "gainDb": self.gain_db,
            "ducking": self.ducking,
        }


def validate_narration_fit(
    selection: NarrationSelection,
    sample_count: int,
    sample_rate: int,
    output_frames: int,
    fps: int,
) -> None:
    selection = NarrationSelection.from_json(selection.to_json())
    if any(type(n) is not int or n <= 0 for n in (sample_count, sample_rate, output_frames, fps)):
        raise ValueError("Narration and output clocks require positive integer counts.")
    if (
        selection.start_frame >= output_frames
        or sample_count * fps > (output_frames - selection.start_frame) * sample_rate
    ):
        raise ValueError(
            f"Narration lasts {sample_count / sample_rate:.3f} seconds; "
            f"available output is {max(0, output_frames - selection.start_frame) / fps:.3f} seconds."
        )
