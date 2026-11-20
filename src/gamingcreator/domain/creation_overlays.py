"""Immutable output-frame overlays. Asset registration and rasterization live outside domain."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

OVERLAYS_VERSION = "creation-overlays-v1"
MAX_OVERLAYS = 16
MAX_ASSET_BYTES = 8 * 1024 * 1024
MAX_ASSET_PIXELS = 16_000_000
MAX_DECODED_BYTES = 128 * 1024 * 1024
_FIELDS = {
    "overlayId",
    "kind",
    "startFrame",
    "endFrame",
    "x",
    "y",
    "width",
    "fadeInFrames",
    "fadeOutFrames",
    "assetId",
    "assetReceiptSha256",
}


def _integer(value: int, minimum: int, maximum: int, name: str) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Invalid overlay {name}.")


def _hex(value: str, length: int) -> None:
    if not isinstance(value, str) or re.fullmatch(f"[0-9a-f]{{{length}}}", value) is None:
        raise ValueError("Invalid overlay identity.")


def validate_overlay_text(value: object) -> str:
    """Validate the shared sprite/domain text contract without rewriting text."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 120
        or any(c in value for c in "{}\\<>")
        or any(unicodedata.category(c).startswith("C") or c in "\u2028\u2029" for c in value)
    ):
        raise ValueError("Overlay text must be 1..120 single-line plain characters.")
    return value


@dataclass(frozen=True, slots=True)
class OverlayItem:
    overlay_id: str
    kind: str
    start_frame: int
    end_frame: int
    x: int
    y: int
    width: int
    fade_in_frames: int
    fade_out_frames: int
    asset_id: str
    asset_receipt_sha256: str
    text: str | None = None

    def __post_init__(self) -> None:
        _hex(self.overlay_id, 32)
        _hex(self.asset_id, 32)
        _hex(self.asset_receipt_sha256, 64)
        if self.kind not in ("text", "image"):
            raise ValueError("Unsupported overlay kind.")
        # No arbitrary source-duration ceiling: these are output timeline frames.
        if type(self.start_frame) is not int or self.start_frame < 0:
            raise ValueError("Invalid overlay start frame.")
        if type(self.end_frame) is not int or self.end_frame <= self.start_frame:
            raise ValueError("Invalid overlay end frame.")
        _integer(self.x, 0, 10000, "x")
        _integer(self.y, 0, 10000, "y")
        _integer(self.width, 1, 10000, "width")
        if self.x + self.width > 10000:
            raise ValueError("Overlay width exceeds canvas.")
        duration = self.end_frame - self.start_frame
        _integer(self.fade_in_frames, 0, duration, "fade in")
        _integer(self.fade_out_frames, 0, duration, "fade out")
        if self.fade_in_frames + self.fade_out_frames > duration:
            raise ValueError("Overlay fades exceed duration.")
        if self.kind == "image" and self.text is not None:
            raise ValueError("Image overlay cannot contain text.")
        if self.kind == "text":
            validate_overlay_text(self.text)

    @classmethod
    def from_json(cls, value: object) -> OverlayItem:
        if not isinstance(value, dict):
            raise ValueError("Invalid overlay item.")
        expected = _FIELDS | ({"text"} if value.get("kind") == "text" else set())
        if set(value) != expected:
            raise ValueError("Invalid overlay item fields.")
        return cls(
            value["overlayId"],
            value["kind"],
            value["startFrame"],
            value["endFrame"],
            value["x"],
            value["y"],
            value["width"],
            value["fadeInFrames"],
            value["fadeOutFrames"],
            value["assetId"],
            value["assetReceiptSha256"],
            value.get("text"),
        )

    def to_json(self) -> dict[str, Any]:
        result = {
            "overlayId": self.overlay_id,
            "kind": self.kind,
            "startFrame": self.start_frame,
            "endFrame": self.end_frame,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "fadeInFrames": self.fade_in_frames,
            "fadeOutFrames": self.fade_out_frames,
            "assetId": self.asset_id,
            "assetReceiptSha256": self.asset_receipt_sha256,
        }
        if self.kind == "text":
            result["text"] = self.text
        return result

    def opacity_at(self, output_frame: int) -> Fraction:
        if type(output_frame) is not int:
            raise ValueError("Output frame must be an integer.")
        if not self.start_frame <= output_frame < self.end_frame:
            return Fraction(0)
        fade_in = (
            Fraction(output_frame - self.start_frame, self.fade_in_frames)
            if self.fade_in_frames
            else Fraction(1)
        )
        fade_out = (
            Fraction(self.end_frame - output_frame, self.fade_out_frames)
            if self.fade_out_frames
            else Fraction(1)
        )
        return min(Fraction(1), fade_in, fade_out)


@dataclass(frozen=True, slots=True)
class CreationOverlays:
    """Items are ordered bottom to top; an empty tuple explicitly clears overlays."""

    items: tuple[OverlayItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or len(self.items) > MAX_OVERLAYS:
            raise ValueError("Overlays must be a tuple of at most 16 items.")
        if any(not isinstance(item, OverlayItem) for item in self.items):
            raise ValueError("Invalid overlay item.")
        if len({item.overlay_id for item in self.items}) != len(self.items):
            raise ValueError("Duplicate overlay identity.")

    @classmethod
    def from_json(cls, value: object) -> CreationOverlays:
        if not isinstance(value, dict) or set(value) != {"schemaVersion", "items"}:
            raise ValueError("Invalid overlays fields.")
        if value["schemaVersion"] != OVERLAYS_VERSION or not isinstance(value["items"], list):
            raise ValueError("Invalid overlays schema or items.")
        return cls(tuple(OverlayItem.from_json(item) for item in value["items"]))

    def to_json(self) -> dict[str, Any]:
        return {"schemaVersion": OVERLAYS_VERSION, "items": [item.to_json() for item in self.items]}

    def sha256(self) -> str:
        """Hash UTF-8 canonical JSON; object key order is irrelevant, layer order is not."""
        canonical = json.dumps(
            self.to_json(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def validate_duration(self, total_frames: int) -> None:
        if type(total_frames) is not int or total_frames < 0:
            raise ValueError("Invalid output duration.")
        if any(item.end_frame > total_frames for item in self.items):
            raise ValueError("Overlay extends beyond output duration.")


def _round_ratio(numerator: int, denominator: int) -> int:
    """Nonnegative integer half-up rounding, shared by preview and export."""
    return (2 * numerator + denominator) // (2 * denominator)


def overlay_pixel_geometry(
    item: OverlayItem,
    output_width: int,
    output_height: int,
    asset_width: int,
    asset_height: int,
) -> tuple[int, int, int, int]:
    """Return x, y, width, height; preserve sprite aspect ratio and reject overflow."""
    for dimension in (output_width, output_height, asset_width, asset_height):
        if type(dimension) is not int or dimension <= 0:
            raise ValueError("Overlay dimensions must be positive integers.")
    x = _round_ratio(item.x * output_width, 10000)
    y = _round_ratio(item.y * output_height, 10000)
    width = max(1, _round_ratio(item.width * output_width, 10000))
    height = max(1, _round_ratio(width * asset_height, asset_width))
    if x + width > output_width or y + height > output_height:
        raise ValueError("Overlay sprite exceeds output canvas.")
    return x, y, width, height


@dataclass(frozen=True, slots=True)
class OverlayAssetMetadata:
    """Trusted decoder results; this class cannot establish PNG authenticity itself."""

    asset_id: str
    asset_receipt_sha256: str
    byte_size: int
    width: int
    height: int
    media_type: str = "image/png"

    def __post_init__(self) -> None:
        _hex(self.asset_id, 32)
        _hex(self.asset_receipt_sha256, 64)
        _integer(self.byte_size, 1, MAX_ASSET_BYTES, "asset bytes")
        _integer(self.width, 1, 4096, "asset width")
        _integer(self.height, 1, 4096, "asset height")
        if self.media_type != "image/png" or self.width * self.height > MAX_ASSET_PIXELS:
            raise ValueError("Unsupported overlay image or pixel budget exceeded.")


def validate_asset_budget(
    overlays: CreationOverlays, assets: tuple[OverlayAssetMetadata, ...]
) -> None:
    """Require exact references; count each distinct RGBA sprite once per version."""
    by_id: dict[str, OverlayAssetMetadata] = {}
    for asset in assets:
        if not isinstance(asset, OverlayAssetMetadata):
            raise ValueError("Invalid overlay asset metadata.")
        if asset.asset_id in by_id and by_id[asset.asset_id] != asset:
            raise ValueError("Conflicting overlay asset metadata.")
        by_id[asset.asset_id] = asset
    required = {item.asset_id for item in overlays.items}
    if set(by_id) != required:
        raise ValueError("Overlay assets do not match selected references.")
    for item in overlays.items:
        if by_id[item.asset_id].asset_receipt_sha256 != item.asset_receipt_sha256:
            raise ValueError("Overlay asset receipt mismatch.")
    if sum(asset.width * asset.height * 4 for asset in by_id.values()) > MAX_DECODED_BYTES:
        raise ValueError("Overlay decoded asset budget exceeded.")
