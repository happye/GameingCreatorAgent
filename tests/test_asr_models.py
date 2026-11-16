"""Installed local ASR model selection uses the existing pin identity only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from gamingcreator.cli.main import _pinned_asr_settings
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.asr_models import (
    load_pinned_asr_settings,
    select_installed_asr_settings,
)

MODEL = "Systran/faster-whisper-tiny"
REVISION = "d90ca5fe260221311c53c58e660288d3deb8d356"
FILES = (
    ("model.bin", 11),
    ("config.json", 12),
    ("tokenizer.json", 13),
    ("vocabulary.txt", 14),
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_catalog(repository: Path, *, install_files: bool = True, model: str = MODEL) -> Path:
    references = repository / "docs" / "references"
    references.mkdir(parents=True)
    rows = []
    model_directory = repository / ".cache" / "models" / "faster-whisper" / "tiny" / REVISION
    if install_files:
        model_directory.mkdir(parents=True)
    for name, size in FILES:
        payload = b"x" * size
        if install_files:
            (model_directory / name).write_bytes(payload)
        rows.append({"name": name, "size": size, "sha256": _digest(payload)})
    pin_path = references / "asr-models.json"
    pin_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "model": model,
                "revision": REVISION,
                "files": rows,
            }
        ),
        encoding="utf-8",
    )
    version = "14.51.36247"
    native_directory = repository / ".tools" / "native" / "msvc" / version
    native_directory.mkdir(parents=True)
    library = native_directory / "msvcp140.dll"
    library.write_bytes(b"native-dll")
    (references / "asr-native-toolchain.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "version": version,
                "files": {"msvcp140.dll": _digest(library.read_bytes())},
            }
        ),
        encoding="utf-8",
    )
    return pin_path


def test_select_records_actual_installed_model_and_revision(tmp_path):
    pin_path = _write_catalog(tmp_path)
    before = pin_path.read_bytes()
    settings = select_installed_asr_settings(tmp_path, MODEL)
    assert settings.model_name == MODEL
    assert settings.model_revision == REVISION
    assert (
        settings.model_directory
        == tmp_path / ".cache" / "models" / "faster-whisper" / "tiny" / REVISION
    )
    assert {item.name for item in settings.model_files} == {name for name, _ in FILES}
    assert pin_path.read_bytes() == before


def test_unknown_or_missing_model_is_unavailable_and_does_not_change_config(tmp_path):
    pin_path = _write_catalog(tmp_path)
    before = pin_path.read_bytes()
    with pytest.raises(AppError) as error:
        select_installed_asr_settings(tmp_path, "openai/whisper-tiny")
    assert error.value.code == "environment.asr"
    assert error.value.exit_code == ExitCode.ENVIRONMENT
    assert error.value.message == "本机没有安装这个识别模型。"
    assert pin_path.read_bytes() == before

    missing = tmp_path / "empty"
    missing.mkdir()
    with pytest.raises(AppError) as missing_pin:
        select_installed_asr_settings(missing, MODEL)
    assert missing_pin.value.message == "本地 ASR 模型清单不可用。"
    assert not (missing / "docs").exists()


def test_known_name_with_missing_files_is_unavailable(tmp_path):
    _write_catalog(tmp_path, install_files=False)
    with pytest.raises(AppError) as error:
        select_installed_asr_settings(tmp_path, MODEL)
    assert error.value.message == "本机没有安装这个识别模型。"
    assert not (tmp_path / ".cache" / "models").exists()


def test_cli_pinned_settings_still_load_the_same_identity(tmp_path):
    _write_catalog(tmp_path)
    pinned = _pinned_asr_settings(tmp_path)
    loaded = load_pinned_asr_settings(tmp_path)
    assert pinned == loaded
    assert pinned.model_name == MODEL and pinned.model_revision == REVISION
