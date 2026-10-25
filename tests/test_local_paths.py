"""Containment paths stay exact while other threads create or delete their parents (TD012)."""

import sys
import threading
import time
from pathlib import Path

import pytest

from gamingcreator.infrastructure.local_paths import is_link, resolve_existing


def link_directory(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


def test_missing_tail_is_joined_to_the_resolved_existing_part(tmp_path):
    root = tmp_path.resolve()
    (root / "artifacts").mkdir()
    assert resolve_existing(root / "artifacts" / "new" / "deeper") == root / "artifacts/new/deeper"
    assert resolve_existing(root / "artifacts" / ".." / "outside") == root / "outside"
    assert not str(resolve_existing(root / "artifacts" / "new")).startswith("\\\\?\\")


@pytest.mark.parametrize("tail", ["new/G:foo", "G:../x", "new/x:stream", "G:..\\G:..\\x"])
def test_drive_or_stream_like_missing_components_are_refused(tmp_path, tail):
    root = tmp_path.resolve()
    (root / "artifacts").mkdir()
    # Joined as one relative value, as preparation_project receives it from a request.
    with pytest.raises(OSError):
        resolve_existing(root / Path("artifacts/" + tail))


def test_links_in_the_existing_part_are_followed(tmp_path):
    root = tmp_path.resolve()
    (root / "artifacts").mkdir()
    (root / "outside").mkdir()
    link_directory(root / "artifacts" / "linked", root / "outside")
    assert resolve_existing(root / "artifacts" / "linked" / "project") == root / "outside/project"
    assert is_link(root / "artifacts" / "linked")
    assert not is_link(root / "artifacts")
    assert not is_link(root / "artifacts" / "missing")


def test_dangling_link_is_refused_not_treated_as_missing(tmp_path):
    root = tmp_path.resolve()
    (root / "artifacts").mkdir()
    victim = root / "outside" / "victim"
    victim.mkdir(parents=True)
    link_directory(root / "artifacts" / "proj", victim)
    victim.rmdir()
    with pytest.raises(OSError):
        resolve_existing(root / "artifacts" / "proj")
    with pytest.raises(OSError):
        resolve_existing(root / "artifacts" / "proj" / "timeline.sqlite3")
    from gamingcreator.domain.errors import AppError
    from gamingcreator.ui.media_preparation import preparation_project

    with pytest.raises(AppError):
        preparation_project(root, "artifacts/proj")
    assert not (root / "outside" / "victim").exists()


def test_parent_created_concurrently_never_yields_a_foreign_path(tmp_path):
    """A running job creates project folders while a request resolves a path below them."""
    root = tmp_path.resolve()
    created = [0]
    stop = threading.Event()

    def create() -> None:
        while not stop.is_set() and created[0] < 100_000:
            (root / str(created[0]) / "artifacts").mkdir(parents=True)
            created[0] += 1

    worker = threading.Thread(target=create)
    worker.start()
    wrong: list[str] = []
    old_wrong = 0
    try:
        began = time.monotonic()
        while time.monotonic() - began < 1:
            # The folder the worker is about to create, so creation races the lookup.
            requested = root / str(created[0] + 1) / "artifacts" / "other"
            result = resolve_existing(requested)
            if result != requested:
                wrong.append(str(result))
            requested = root / str(created[0] + 1) / "artifacts" / "other"
            old_wrong += requested.resolve() != requested
    finally:
        stop.set()
        worker.join()
    assert wrong == []
    if sys.platform == "win32" and old_wrong == 0:
        pytest.skip("this run did not hit the Path.resolve() race it guards against")
