"""Local knowledge directory import: txt/md batch, optional media flag, no crawling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gamingcreator.application.knowledge_import import (
    import_knowledge_directory_sync,
    list_import_candidates,
)
from gamingcreator.infrastructure.knowledge_store import KnowledgeStore
from gamingcreator.infrastructure.local_paths import is_link


def _folder(tmp_path: Path) -> Path:
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "skill.txt").write_text("释放技能前先读条。", encoding="utf-8")
    (folder / "patch.md").write_text("# 补丁\n\n新英雄上线。\n", encoding="utf-8")
    (folder / "ignore.bin").write_bytes(b"\x00\x01")
    (folder / "shot.png").write_bytes(b"not-a-real-png-but-suffix-only")
    return folder


def test_lists_text_by_default_and_media_when_enabled(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    names = [path.name for path in list_import_candidates(folder)]
    assert names == ["patch.md", "skill.txt"]
    with_media = [path.name for path in list_import_candidates(folder, include_media=True)]
    assert "shot.png" in with_media
    assert "ignore.bin" not in with_media


def test_refuses_missing_or_linked_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="不存在"):
        list_import_candidates(tmp_path / "missing")
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    if not is_link(link):
        pytest.skip("symlink not reported as link")
    with pytest.raises(ValueError, match="符号链接|普通文件夹"):
        list_import_candidates(link)


def test_batch_import_writes_entries_with_source_notes(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    store = KnowledgeStore(repo)
    report = import_knowledge_directory_sync(
        store,
        game="代号Atom",
        directory=folder,
        source_kind="wiki",
        source_label="本地攻略夹",
        include_media=False,
        scratch=repo / ".cache/workspace/knowledge-import",
    )
    assert report["schemaVersion"] == "knowledge-directory-import-v1"
    assert report["summary"]["imported"] == 2
    assert report["summary"]["failed"] == 0
    entries = store.entries()
    assert len(entries) == 2
    labels = {entry["source"]["label"] for entry in entries}
    assert all("目录导入" in label for label in labels)
    assert any("skill.txt" in label for label in labels)
    titles = {entry["title"] for entry in entries}
    assert titles == {"skill", "patch"}

    again = import_knowledge_directory_sync(
        store,
        game="代号Atom",
        directory=folder,
        source_kind="wiki",
        source_label="本地攻略夹",
        include_media=False,
        scratch=repo / ".cache/workspace/knowledge-import",
    )
    assert again["summary"]["imported"] == 0
    assert again["summary"]["skipped"] == 2


def test_include_media_false_does_not_touch_png(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    store = KnowledgeStore(tmp_path / "repo2")
    report = import_knowledge_directory_sync(
        store,
        game="GameX",
        directory=folder,
        source_kind="user",
        source_label="笔记",
        include_media=False,
    )
    assert all(item["file"].endswith((".txt", ".md")) for item in report["items"])
    assert report["summary"]["considered"] == 2


def test_http_directory_import(tmp_path: Path) -> None:
    from gamingcreator.ui.server import create_server

    folder = _folder(tmp_path)
    repo = tmp_path / "http-repo"
    repo.mkdir()
    server = create_server("127.0.0.1", 0, repo)
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import urllib.request

        body = json.dumps(
            {
                "game": "HTTPGame",
                "directory": str(folder),
                "sourceKind": "official",
                "sourceLabel": "测试目录",
                "includeMedia": False,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/knowledge-import",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["summary"]["imported"] == 2
        assert KnowledgeStore(repo).entries()
    finally:
        server.shutdown()