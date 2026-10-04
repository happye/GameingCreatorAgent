import json
import re
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
        if not isinstance(raw, dict) or type(raw.get("schemaVersion")) is not int:
            raise invalid_config()
        schema_version = raw["schemaVersion"]
        if schema_version not in (1, 2):
            raise invalid_config()
        fields = {"schemaVersion", "vision", "limits"}
        if schema_version == 2:
            fields |= {"sampling", "asr"}
        config = _object(raw, fields)
        vision_fields = {"provider", "model"}
        if schema_version == 2:
            vision_fields |= {"priceVersion", "maxOutputTokens"}
            if isinstance(config["vision"], dict) and "promptVersion" in config["vision"]:
                vision_fields |= {"promptVersion", "promptHash"}
        vision = _object(config["vision"], vision_fields)
        limits = _object(config["limits"], {"maxRequests", "maxInputFrames"})
        extra: dict[str, object] = {}
        if schema_version == 2:
            sampling = _object(config["sampling"], {"intervalMs", "windowFrames", "windowOverlap"})
            asr = _object(config["asr"], {"language"})
            interval = _positive_int(sampling["intervalMs"])
            window = _positive_int(sampling["windowFrames"])
            overlap = sampling["windowOverlap"]
            output = _positive_int(vision["maxOutputTokens"])
            language = _text(asr["language"])
            prompt_version = _text(vision.get("promptVersion", "phase0-vision-v1"))
            temporal = prompt_version in (
                "phase0-vision-v3",
                "phase0-vision-v4",
                "phase0-vision-v5",
            )
            if (
                type(overlap) is not int
                or not 0 <= overlap < window
                or window > (9 if temporal else 5)
                or (temporal and window < 2)
                or not 100 <= interval <= 60000
                or output > 4096
                or language not in ("zh", "en", "auto")
            ):
                raise invalid_config()
            extra = {
                "schema_version": 2,
                "price_version": _text(vision["priceVersion"]),
                "sampling_interval_ms": interval,
                "window_frames": window,
                "window_overlap": overlap,
                "max_output_tokens": output,
                "asr_language": language,
            }
            if "promptVersion" in vision:
                prompt_version = _text(vision["promptVersion"])
                prompt_hash = _text(vision["promptHash"])
                if prompt_version not in (
                    "phase0-vision-v1",
                    "phase0-vision-v2",
                    "phase0-vision-v3",
                    "phase0-vision-v4",
                    "phase0-vision-v5",
                ) or not re.fullmatch(r"[a-f0-9]{64}", prompt_hash):
                    raise invalid_config()
                extra.update(vision_prompt_version=prompt_version, vision_prompt_hash=prompt_hash)
        return AnalysisConfig(
            provider=_text(vision["provider"]),
            model=_text(vision["model"]),
            max_requests=_positive_int(limits["maxRequests"]),
            max_input_frames=_positive_int(limits["maxInputFrames"]),
            **extra,  # type: ignore[arg-type]
        )
