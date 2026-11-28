from pathlib import Path

import pytest

from gamingcreator.domain.errors import AppError
from gamingcreator.ui import studio_local_picker as picker


def test_native_selection_stays_local(tmp_path, monkeypatch):
    project = tmp_path / "artifacts" / "新建剪辑"
    project.mkdir(parents=True)
    video = tmp_path / "GameVideos" / "玩法演示.mp4"
    selected = {"project": [str(project)], "videos": [str(video)]}
    monkeypatch.setattr(picker, "_windows_dialog", lambda repository, kind: selected[kind])

    assert picker.studio_local_picker(tmp_path, {"kind": "project"}) == {
        "paths": ["artifacts/新建剪辑"]
    }
    assert picker.studio_local_picker(tmp_path, {"kind": "videos"}) == {"paths": [str(video)]}

    selected["project"] = [str(tmp_path)]
    with pytest.raises(AppError, match="artifacts"):
        picker.studio_local_picker(tmp_path, {"kind": "project"})

    selected["project"] = []
    assert picker.studio_local_picker(tmp_path, {"kind": "project"}) == {"paths": []}


def test_native_picker_rejects_extra_request_fields(tmp_path: Path):
    with pytest.raises(ValueError, match="local picker kind"):
        picker.studio_local_picker(tmp_path, {"kind": "videos", "path": str(tmp_path)})
