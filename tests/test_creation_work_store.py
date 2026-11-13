from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure import creation_work_store
from gamingcreator.infrastructure.creation_work_store import CreationWorkStore
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock

WORK_ID = "a" * 32


def test_restart_reuses_identity_without_changing_bytes(tmp_path: Path) -> None:
    root = tmp_path / "works"
    first = CreationWorkStore(root).create("project-a", WORK_ID)
    path = root / f"{WORK_ID}.json"
    original = path.read_bytes()
    restarted = CreationWorkStore(root)
    assert restarted.create("project-a", WORK_ID) == first
    assert restarted.read(WORK_ID, "project-a") == first
    assert path.read_bytes() == original
    assert first["schemaVersion"] == "creation-work-v1"
    assert str(first["createdAt"]).endswith("+00:00")


def test_cross_project_refused_without_replacing_record(tmp_path: Path) -> None:
    store = CreationWorkStore(tmp_path)
    store.create("project-a", WORK_ID)
    original = (tmp_path / f"{WORK_ID}.json").read_bytes()
    with pytest.raises(ValueError):
        store.create("project-b", WORK_ID)
    with pytest.raises(ValueError):
        store.read(WORK_ID, "project-b")
    assert (tmp_path / f"{WORK_ID}.json").read_bytes() == original


@pytest.mark.parametrize("damage", ["tamper", "broken", "schema", "identity"])
def test_invalid_record_is_never_replaced(tmp_path: Path, damage: str) -> None:
    store = CreationWorkStore(tmp_path)
    record = store.create("project-a", WORK_ID)
    path = tmp_path / f"{WORK_ID}.json"
    if damage == "broken":
        path.write_text("{", encoding="utf-8")
    else:
        field = {"tamper": "projectId", "schema": "schemaVersion", "identity": "workId"}
        record[field[damage]] = "changed"
        if damage != "tamper":
            payload = {key: value for key, value in record.items() if key != "documentSha256"}
            canonical = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            record["documentSha256"] = hashlib.sha256(canonical.encode()).hexdigest()
        path.write_text(json.dumps(record), encoding="utf-8")
    original = path.read_bytes()
    with pytest.raises(ValueError):
        store.read(WORK_ID)
    with pytest.raises(ValueError):
        store.create("project-a", WORK_ID)
    assert path.read_bytes() == original


def test_read_does_not_create_root_or_work(tmp_path: Path) -> None:
    root = tmp_path / "works"
    with pytest.raises(ValueError):
        CreationWorkStore(root).read(WORK_ID)
    assert not root.exists()


def test_catalog_missing_root_does_not_create_it(tmp_path: Path) -> None:
    root = tmp_path / "works"
    assert CreationWorkStore(root).catalog("project-a") == []
    assert not root.exists()


def test_catalog_filters_projects_and_sorts_newest_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    class Clock:
        current = datetime(2026, 11, 13, tzinfo=UTC)

        @classmethod
        def now(cls, timezone: object) -> datetime:
            return cls.current

    monkeypatch.setattr(creation_work_store, "datetime", Clock)
    store = CreationWorkStore(tmp_path)
    first = store.create("project-a", "b" * 32)
    store.create("project-b", "c" * 32)
    tied = store.create("project-a", "a" * 32)
    Clock.current = datetime(2026, 11, 14, tzinfo=UTC)
    latest = store.create("project-a", "d" * 32)
    assert store.catalog("project-a") == [latest, tied, first]
    assert store.catalog("project-a") == [latest, tied, first]


def test_catalog_rejects_corruption_even_in_other_project(tmp_path: Path) -> None:
    store = CreationWorkStore(tmp_path)
    store.create("project-a", WORK_ID)
    other_id = "b" * 32
    store.create("project-b", other_id)
    (tmp_path / f"{other_id}.json").write_bytes(b"{")
    with pytest.raises(ValueError):
        store.catalog("project-a")


@pytest.mark.parametrize("work_id", ["", "a" * 31, "A" * 32, "g" * 32, "../escape"])
def test_invalid_request_id_creates_nothing(tmp_path: Path, work_id: str) -> None:
    root = tmp_path / "works"
    with pytest.raises(ValueError):
        CreationWorkStore(root).create("project-a", work_id)
    assert not root.exists()


def _symlink(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError:
        pytest.skip("Symlink creation unavailable")


def test_linked_root_and_parent_are_refused(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    _symlink(link, target, directory=True)
    for root in (link, link / "works"):
        with pytest.raises(ValueError):
            CreationWorkStore(root)
    assert list(target.iterdir()) == []


def test_catalog_rejects_root_linked_after_initialization(tmp_path: Path) -> None:
    root = tmp_path / "works"
    store = CreationWorkStore(root)
    target = tmp_path / "target"
    target.mkdir()
    _symlink(root, target, directory=True)
    with pytest.raises(ValueError):
        store.catalog("project-a")


def test_linked_record_is_refused(tmp_path: Path) -> None:
    store = CreationWorkStore(tmp_path)
    store.create("project-a", WORK_ID)
    target = tmp_path / f"{WORK_ID}.json"
    linked_id = "b" * 32
    _symlink(tmp_path / f"{linked_id}.json", target)
    original = target.read_bytes()
    with pytest.raises(ValueError):
        store.read(linked_id)
    with pytest.raises(ValueError):
        store.create("project-a", linked_id)
    assert target.read_bytes() == original


def test_lock_conflict_leaves_no_record_then_retry_reuses(tmp_path: Path) -> None:
    lock = ProjectWriterLock(tmp_path)
    lock.acquire()
    store = CreationWorkStore(tmp_path)
    try:
        with pytest.raises(AppError, match="写入进程"):
            store.create("project-a", WORK_ID)
        assert list(tmp_path.glob("*.json")) == []
    finally:
        lock.close()
    first = store.create("project-a", WORK_ID)
    assert store.create("project-a", WORK_ID) == first
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_partial_write_is_preserved_and_future_create_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_write(path: Path, text: str) -> None:
        path.write_bytes(b"{")
        raise ValueError("simulated write failure")

    store = CreationWorkStore(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(creation_work_store, "write_exclusive_text", fail_write)
        with pytest.raises(ValueError, match="simulated"):
            store.create("project-a", WORK_ID)
    with pytest.raises(ValueError):
        store.create("project-a", WORK_ID)
    assert (tmp_path / f"{WORK_ID}.json").read_bytes() == b"{"
