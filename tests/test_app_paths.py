"""App path helpers for scripts/ and packaged model weights."""

from pathlib import Path

import pytest

from gamingcreator.infrastructure.app_paths import model_directory


def test_model_directory_prefers_cache_models(tmp_path: Path) -> None:
    cached = tmp_path / ".cache/models/faster-whisper/tiny/abcd"
    cached.mkdir(parents=True)
    packaged = tmp_path / "models/faster-whisper/tiny/abcd"
    packaged.mkdir(parents=True)
    assert model_directory(tmp_path, "faster-whisper", "tiny", "abcd") == cached.resolve()


def test_model_directory_falls_back_to_packaged_models(tmp_path: Path) -> None:
    packaged = tmp_path / "models/multilingual-e5-small/rev"
    packaged.mkdir(parents=True)
    assert (
        model_directory(tmp_path, "multilingual-e5-small", "rev") == packaged.resolve()
    )


def test_model_directory_returns_packaged_path_when_neither_exists(tmp_path: Path) -> None:
    expected = (tmp_path / "models/faster-whisper/tiny/missing").resolve()
    assert model_directory(tmp_path, "faster-whisper", "tiny", "missing") == expected


def test_model_directory_requires_parts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        model_directory(tmp_path)
