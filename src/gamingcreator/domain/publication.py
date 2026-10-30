"""Local editable publication metadata, without platform or AI claims."""

import unicodedata
from typing import Any


def validate_metadata(value: dict[str, Any], frames: int) -> None:
    def text(item: object, minimum: int, maximum: int) -> bool:
        return (
            isinstance(item, str)
            and minimum <= len(item) <= maximum
            and (not minimum or bool(item.strip()))
            and not any(unicodedata.category(char) == "Cc" for char in item)
        )

    tags = value.get("tags")
    if (
        type(value.get("coverFrame")) is not int
        or not 0 <= value["coverFrame"] < frames
        or not text(value.get("title"), 1, 200)
        or not text(value.get("description"), 0, 5000)
        or not isinstance(tags, list)
        or len(tags) > 20
        or any(not text(tag, 1, 50) for tag in tags)
        or len(tags) != len(set(tags))
    ):
        raise ValueError("Invalid local publication metadata or output frame.")
