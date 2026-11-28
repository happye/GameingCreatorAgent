import os
from pathlib import Path

import pytest

from gamingcreator.domain.errors import AppError
from gamingcreator.ui import studio_local_picker as picker


def test_native_selection_stays_local(tmp_path, monkeypatch):
    video = tmp_path / "GameVideos" / "玩法演示.mp4"
    selected = [str(video)]
    monkeypatch.setattr(picker, "_windows_dialog", lambda repository: selected)

    assert picker.studio_local_picker(tmp_path, {"kind": "videos"}) == {"paths": [str(video)]}

    selected.clear()
    assert picker.studio_local_picker(tmp_path, {"kind": "videos"}) == {"paths": []}


def test_native_picker_rejects_extra_request_fields(tmp_path: Path):
    with pytest.raises(ValueError, match="local picker kind"):
        picker.studio_local_picker(tmp_path, {"kind": "videos", "path": str(tmp_path)})
    with pytest.raises(ValueError, match="local picker kind"):
        picker.studio_local_picker(tmp_path, {"kind": "project"})


def test_browse_project_locations_and_reject_escaping_paths(tmp_path: Path):
    assert picker.studio_project_locations(tmp_path, "artifacts") == {
        "folder": "artifacts",
        "folders": [],
        "projects": [],
        "histories": [],
    }
    parent = tmp_path / "artifacts" / "工作目录"
    project = parent / "已建"
    project.mkdir(parents=True)
    (project / "timeline.sqlite3").touch()
    unrelated = parent / "外链数据库"
    unrelated.mkdir()
    outside = tmp_path / "outside.sqlite3"
    outside.touch()
    os.link(outside, unrelated / "timeline.sqlite3")

    assert picker.studio_project_locations(tmp_path, "artifacts") == {
        "folder": "artifacts",
        "folders": [{"path": "artifacts/工作目录", "name": "工作目录"}],
        "projects": [],
        "histories": [],
    }
    locations = picker.studio_project_locations(tmp_path, "artifacts/工作目录")
    assert locations["projects"] == [{"path": "artifacts/工作目录/已建", "name": "已建"}]
    assert locations["folders"] == [
        {"path": "artifacts/工作目录/外链数据库", "name": "外链数据库"},
        {"path": "artifacts/工作目录/已建", "name": "已建"},
    ]
    assert (
        picker.studio_project_locations(tmp_path, "artifacts/工作目录/已建")["projects"]
        == locations["projects"]
    )

    for folder in ("artifacts/../", "artifacts/missing", str(tmp_path)):
        with pytest.raises(AppError, match="artifacts"):
            picker.studio_project_locations(tmp_path, folder)


def test_frozen_batch_discovered_without_database(tmp_path: Path):
    folder = "artifacts/frozen"
    project = tmp_path / folder
    batch = project / "media-batches" / ("1" * 32)
    batch.mkdir(parents=True)
    for name in ("source-input.json", "analysis-config.json", "plan.json", "receipt.json"):
        (batch / name).touch()
    expected = [{"path": folder, "name": "frozen"}]
    assert picker.studio_project_locations(tmp_path, "artifacts")["histories"] == expected
    assert picker.studio_project_locations(tmp_path, folder)["histories"] == expected

    (project / "timeline.sqlite3").touch()
    assert picker.studio_project_locations(tmp_path, "artifacts")["histories"] == []
    assert picker.studio_project_locations(tmp_path, "artifacts")["projects"] == expected

    (project / "timeline.sqlite3").unlink()
    (batch / "receipt.json").unlink()
    assert picker.studio_project_locations(tmp_path, "artifacts")["histories"] == []
