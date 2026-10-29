"""Explicit offline creation inputs; source time never denotes output frames."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreativeBrief:
    game: str
    content_type: str
    platforms: tuple[str, ...]
    target_duration: int
    objective: str
    audience: str
    tone: str
    mandatory_topics: tuple[str, ...]
    exclude: tuple[str, ...]

    @classmethod
    def from_json(cls, value: object) -> "CreativeBrief":
        if not isinstance(value, dict) or set(value) != {
            "game",
            "contentType",
            "platforms",
            "targetDuration",
            "objective",
            "audience",
            "tone",
            "mandatoryTopics",
            "exclude",
        }:
            raise ValueError("Brief must contain exactly the fields in product specification §22.")
        for key in ("game", "contentType", "objective", "audience", "tone"):
            if not isinstance(value[key], str) or not value[key].strip():
                raise ValueError(f"Brief {key} must be nonempty text.")
        for key in ("platforms", "mandatoryTopics", "exclude"):
            items = value[key]
            if (
                not isinstance(items, list)
                or any(not isinstance(item, str) or not item.strip() for item in items)
                or len(items) != len(set(items))
            ):
                raise ValueError(f"Brief {key} must be a unique text array.")
        if not value["platforms"]:
            raise ValueError("Brief needs a platform.")
        duration = value["targetDuration"]
        if type(duration) is not int or not 1 <= duration <= 86400:
            raise ValueError("targetDuration must be integer seconds in 1..86400.")
        return cls(
            value["game"],
            value["contentType"],
            tuple(value["platforms"]),
            duration,
            value["objective"],
            value["audience"],
            value["tone"],
            tuple(value["mandatoryTopics"]),
            tuple(value["exclude"]),
        )
