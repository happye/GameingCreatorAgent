import json
from pathlib import Path
from typing import cast

from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.domain.errors import invalid_config, invalid_video

MAX_CONFIG_BYTES = 1024 * 1024


def _object(value: object, fields: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise invalid_config()
    return cast(dict[str, object], value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise invalid_config()
    return value


def _positive_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise invalid_config()
    return value


class LocalInputReader:
    def validate_video(self, path: Path) -> Path:
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_file():
                raise invalid_video()
            with resolved.open("rb") as stream:
                if not stream.read(1):
                    raise invalid_video()
            return resolved
        except (OSError, ValueError):
            raise invalid_video() from None

    def load_config(self, path: Path) -> AnalysisConfig:
        try:
            with path.open("rb") as stream:
                content = stream.read(MAX_CONFIG_BYTES + 1)
            if len(content) > MAX_CONFIG_BYTES:
                raise invalid_config()
            raw: object = json.loads(content.decode("utf-8-sig"))
        except (OSError, UnicodeError, ValueError):
            raise invalid_config() from None
        config = _object(raw, {"schemaVersion", "vision", "limits"})
        if type(config["schemaVersion"]) is not int or config["schemaVersion"] != 1:
            raise invalid_config()
        vision = _object(config["vision"], {"provider", "model"})
        limits = _object(config["limits"], {"maxRequests", "maxInputFrames"})
        return AnalysisConfig(
            provider=_text(vision["provider"]),
            model=_text(vision["model"]),
            max_requests=_positive_int(limits["maxRequests"]),
            max_input_frames=_positive_int(limits["maxInputFrames"]),
        )
