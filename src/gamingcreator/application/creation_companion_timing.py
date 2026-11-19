"""Place timed assets on preserved shots using validated integer output clocks."""

from fractions import Fraction
from typing import Any


class CompanionTimingError(ValueError):
    """A known placement conflict whose message can be shown in Studio."""


def move_start_frame(
    frame: int,
    before: list[dict[str, Any]],
    after: dict[str, dict[str, Any]],
    fps: int,
    label: str,
) -> int:
    # The incoming clip owns a frame shared by a dissolve, as in the Studio preview.
    anchor = next(
        (
            row
            for row in reversed(before)
            if row["outputStartFrame"] <= frame < row["outputStartFrame"] + row["outputFrames"]
        ),
        None,
    )
    target = after.get(anchor["clipId"]) if anchor is not None else None
    if anchor is None or target is None:
        raise CompanionTimingError(
            f"{label}的起点所在原镜头已删除或替换。请调整指令或取消随原镜移动。"
        )
    step = Fraction(1_000_000, fps)
    source = int(anchor["startUs"]) + (frame - int(anchor["outputStartFrame"])) * step * _speed(
        anchor
    )
    offset = (source - int(target["startUs"])) // (step * _speed(target))
    if not 0 <= offset < target["outputFrames"]:
        raise CompanionTimingError(f"{label}的起点对应画面已裁掉。请调整指令或取消随原镜移动。")
    return int(target["outputStartFrame"]) + offset


def _speed(row: dict[str, Any]) -> Fraction:
    speed = row.get("speed", {"numerator": 1, "denominator": 1})
    return Fraction(speed["numerator"], speed["denominator"])
