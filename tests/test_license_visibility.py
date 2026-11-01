"""Reminders to read bundled THIRD-PARTY-NOTICES.md and gaps.json (no downloads)."""

import json
from pathlib import Path

import pytest


def _load():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "license_visibility.py"
    spec = importlib.util.spec_from_file_location("license_visibility", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_format_lists_paths_and_gap_count(tmp_path: Path) -> None:
    licenses = tmp_path / "licenses"
    licenses.mkdir()
    (licenses / "THIRD-PARTY-NOTICES.md").write_text("# notices\n", encoding="utf-8")
    (licenses / "gaps.json").write_text(
        json.dumps([{"component": "A", "reason": "x"}, {"component": "B", "reason": "y"}]),
        encoding="utf-8",
    )
    module = _load()
    text = module.format_license_visibility(tmp_path)
    assert "THIRD-PARTY-NOTICES.md" in text
    assert "gaps.json" in text
    assert "\u4e0d\u4f1a\u8054\u7f51\u4e0b\u8f7d\u8865\u8bb8\u53ef" in text
    assert "2 \u9879\u5f85\u786e\u8ba4\u7f3a\u53e3" in text
    assert "\u4e0d\u4f1a\u81ea\u52a8\u8865\u9f50" in text


def test_format_warns_when_files_missing(tmp_path: Path) -> None:
    module = _load()
    text = module.format_license_visibility(tmp_path)
    assert "\u8b66\u544a\uff1a\u672a\u627e\u5230 licenses/THIRD-PARTY-NOTICES.md" in text
    assert "\u8b66\u544a\uff1a\u672a\u627e\u5230 licenses/gaps.json" in text


def test_cli_prints_reminder(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    licenses = tmp_path / "licenses"
    licenses.mkdir()
    (licenses / "THIRD-PARTY-NOTICES.md").write_text("# n\n", encoding="utf-8")
    (licenses / "gaps.json").write_text("[]", encoding="utf-8")
    module = _load()
    assert module.main(["--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "gaps.json \u5f53\u524d\u8bb0\u5f55 0 \u9879\u5f85\u786e\u8ba4\u7f3a\u53e3" in out
