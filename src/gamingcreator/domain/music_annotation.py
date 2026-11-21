"""Creator-supplied music tags, intensity and an audio-clock highlight marker."""

from typing import Any

MOODS = ("calm", "lively", "intense", "dramatic", "playful", "electronic")


def annotation_values(value: object, duration_us: int) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"moods", "energy", "dropUs"}:
        raise ValueError("请输入曲目的情绪、力度和高潮点。")
    moods, energy, drop = value["moods"], value["energy"], value["dropUs"]
    if (
        not isinstance(moods, list)
        or len(moods) > len(MOODS)
        or any(not isinstance(mood, str) or mood not in MOODS for mood in moods)
        or len(set(moods)) != len(moods)
    ):
        raise ValueError("曲目情绪标签无效或重复。")
    if energy is not None and (type(energy) is not int or not 0 <= energy <= 100):
        raise ValueError("曲目力度应为 0–100，或留空。")
    if drop is not None and (type(drop) is not int or not 0 <= drop < duration_us):
        raise ValueError("高潮点必须位于曲目时长内。")
    return {"moods": [mood for mood in MOODS if mood in moods], "energy": energy, "dropUs": drop}
