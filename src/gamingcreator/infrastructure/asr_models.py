"""Load the pinned on-device ASR identity and select only an already installed model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from gamingcreator.application.asr import LocalAsrSettings, ModelFile
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.app_paths import model_directory


def load_pinned_asr_settings(repository: Path) -> LocalAsrSettings:
    """Read the repository pin and native file sizes. Does not download or write config."""
    repository = repository.resolve()
    pin_raw: object = json.loads(
        (repository / "docs/references/asr-models.json").read_text(encoding="utf-8")
    )
    native_raw: object = json.loads(
        (repository / "docs/references/asr-native-toolchain.json").read_text(encoding="utf-8")
    )
    if not isinstance(pin_raw, dict) or not isinstance(native_raw, dict):
        raise ValueError
    pin = cast(dict[str, object], pin_raw)
    native = cast(dict[str, object], native_raw)
    file_rows, library_rows = pin["files"], native["files"]
    version, model, revision = native["version"], pin["model"], pin["revision"]
    if (
        not isinstance(file_rows, list)
        or not isinstance(library_rows, dict)
        or not isinstance(version, str)
        or not isinstance(model, str)
        or not isinstance(revision, str)
    ):
        raise ValueError
    model_files: list[ModelFile] = []
    for item in file_rows:
        if not isinstance(item, dict):
            raise ValueError
        row = cast(dict[str, object], item)
        name, size, digest = row["name"], row["size"], row["sha256"]
        if not isinstance(name, str) or type(size) is not int or not isinstance(digest, str):
            raise ValueError
        model_files.append(ModelFile(name, size, digest))
    native_directory = repository / ".tools" / "native" / "msvc" / version
    libraries: list[ModelFile] = []
    for name, digest in cast(dict[object, object], library_rows).items():
        if not isinstance(name, str) or not isinstance(digest, str):
            raise ValueError
        libraries.append(ModelFile(name, (native_directory / name).stat().st_size, digest))
    return LocalAsrSettings(
        model_directory(repository, "faster-whisper", "tiny", revision),
        model,
        revision,
        tuple(model_files),
        native_directory,
        native_library_files=tuple(libraries),
    )


def select_installed_asr_settings(repository: Path, model: str) -> LocalAsrSettings:
    """Return the installed pin identity for an exact model name. Missing is unavailable."""
    try:
        settings = load_pinned_asr_settings(repository)
    except (OSError, ValueError, KeyError, TypeError):
        raise AppError(
            "environment.asr", "本地 ASR 模型清单不可用。", ExitCode.ENVIRONMENT
        ) from None
    directory = settings.model_directory.resolve()
    present = directory.is_dir() and all(
        (directory / item.name).is_file() for item in settings.model_files
    )
    if model != settings.model_name or not present:
        raise AppError("environment.asr", "本机没有安装这个识别模型。", ExitCode.ENVIRONMENT)
    return settings
