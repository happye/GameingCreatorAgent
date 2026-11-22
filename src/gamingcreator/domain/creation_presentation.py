"""Strict local creation presentation: safe-area crop, static corner badge, subtitle style."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

BADGE_CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")
BADGE_MAX_CHARS = 24
SAFE_AREA_MARGIN_MAX = 40
# "standard" is the original burn-in look, so requests without a style render unchanged.
SUBTITLE_STYLES = ("standard", "large", "boxed")
SUBTITLE_FONTS = {"yahei": "Microsoft YaHei", "simsun": "SimSun"}
SUBTITLE_FIELDS = ("subtitleStyle", "subtitleFont", "subtitleColor")
PRESENTATION_FIELDS = ("safeAreaMarginPercent", "badgeText", "badgeCorner", *SUBTITLE_FIELDS)
PRESENTATION_VERSION = "creation-presentation-v1"


def _even_floor(value: int) -> int:
    return value if value % 2 == 0 else value - 1


def safe_area_crop_filter(width: int, height: int, margin_percent: int) -> str:
    """Center-crop by margin percent per side, then scale back to width x height."""
    if margin_percent == 0:
        return ""
    keep = 100 - 2 * margin_percent
    crop_w = max(2, _even_floor(width * keep // 100))
    crop_h = max(2, _even_floor(height * keep // 100))
    if crop_w >= width and crop_h >= height:
        return ""
    x = (width - crop_w) // 2
    y = (height - crop_h) // 2
    return f"crop={crop_w}:{crop_h}:{x}:{y},scale={width}:{height}"


@dataclass(frozen=True, slots=True)
class PresentationOptions:
    safe_area_margin_percent: int = 0
    badge_text: str | None = None
    badge_corner: str = "bottom-left"
    subtitle_style: str = "standard"
    subtitle_font: str | None = None
    subtitle_color: str | None = None

    def __post_init__(self) -> None:
        margin = self.safe_area_margin_percent
        if type(margin) is not int or margin < 0 or margin > SAFE_AREA_MARGIN_MAX:
            raise ValueError("Safe-area margin must be an integer 0..40.")
        text = self.badge_text
        if text is not None:
            if (
                not isinstance(text, str)
                or not text
                or len(text) > BADGE_MAX_CHARS
                or any(char in text for char in "{}\n\r\\")
            ):
                raise ValueError("Badge text must be 1..24 plain characters.")
        if self.badge_corner not in BADGE_CORNERS:
            raise ValueError("Unsupported badge corner.")
        if self.subtitle_style not in SUBTITLE_STYLES:
            raise ValueError("Unsupported subtitle style.")
        font, color = self.subtitle_font, self.subtitle_color
        if font is not None and (not isinstance(font, str) or font not in SUBTITLE_FONTS):
            raise ValueError("Unsupported subtitle font.")
        if color is not None and (
            not isinstance(color, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None
        ):
            raise ValueError("Subtitle color must be #RRGGBB.")

    def without_subtitle_look(self) -> PresentationOptions:
        return replace(self, subtitle_style="standard", subtitle_font=None, subtitle_color=None)

    @property
    def enabled(self) -> bool:
        return (
            self.safe_area_margin_percent > 0
            or self.badge_text is not None
            or self.subtitle_style != "standard"
            or self.subtitle_font is not None
            or self.subtitle_color is not None
        )

    @classmethod
    def from_json(cls, value: object) -> PresentationOptions:
        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise ValueError("Invalid presentation object.")
        if set(value) - set(PRESENTATION_FIELDS):
            raise ValueError("Unknown presentation fields.")
        if any(key in value and value[key] is None for key in ("subtitleFont", "subtitleColor")):
            raise ValueError("Subtitle font and color must be omitted to use defaults.")
        margin = value.get("safeAreaMarginPercent", 0)
        text = value.get("badgeText")
        corner = value.get("badgeCorner", "bottom-left")
        style = value.get("subtitleStyle", "standard")
        return cls(
            margin, text, corner, style, value.get("subtitleFont"), value.get("subtitleColor")
        )

    @classmethod
    def from_request(cls, request: dict[str, Any]) -> PresentationOptions | None:
        payload = {key: request[key] for key in PRESENTATION_FIELDS if key in request}
        return cls.from_json(payload) if payload else None

    def _subtitle_overrides(self) -> dict[str, str]:
        values = {"subtitleFont": self.subtitle_font, "subtitleColor": self.subtitle_color}
        return {key: value for key, value in values.items() if value is not None}

    def to_json(self) -> dict[str, Any]:
        return {
            "safeAreaMarginPercent": self.safe_area_margin_percent,
            "badgeText": self.badge_text,
            "badgeCorner": self.badge_corner,
            "subtitleStyle": self.subtitle_style,
            **self._subtitle_overrides(),
        }

    def receipt(self) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        return {
            "version": PRESENTATION_VERSION,
            "safeArea": (
                {"marginPercent": self.safe_area_margin_percent}
                if self.safe_area_margin_percent > 0
                else None
            ),
            "badge": (
                None
                if self.badge_text is None
                else {"text": self.badge_text, "corner": self.badge_corner}
            ),
            **({"subtitleStyle": self.subtitle_style} if self.subtitle_style != "standard" else {}),
            **self._subtitle_overrides(),
        }
