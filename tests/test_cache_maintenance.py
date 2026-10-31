import ctypes
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "maintenance_under_test", Path(__file__).resolve().parents[1] / "scripts/cache-maintenance.py"
)
assert _spec and _spec.loader
maintenance = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(maintenance)


def test_reclaim_dry_run_and_failed_media(tmp_path):
    cache = tmp_path / ".cache"
    root = cache / "pytest-runs" / "run" / "tmp" / "test_example0"
    root.mkdir(parents=True)
    media = root / "large.nut"
    media.write_bytes(b"x" * (1024 * 1024))
    log = root / "evidence.json"
    log.write_text("{}")
    assert not maintenance.reclaim(root, cache, failed=True)[0]["deleted"]
    assert media.exists()
    result = maintenance.reclaim(root, cache, failed=True, apply=True)
    assert result[0]["deleted"]
    assert not media.exists()
    assert log.exists()
    assert "prefix_sha256" in (root / "media-reclamation.jsonl").read_text()


def test_reject_boundaries_and_protected_paths(tmp_path):
    cache = tmp_path / ".cache"
    root = cache / "workspace" / "test_example0"
    root.mkdir(parents=True)
    assert not maintenance.safe_root(root, cache)
    assert not maintenance.safe_root(tmp_path, cache)
    assert not maintenance.safe_root(cache, cache)


def test_keep_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("GC_KEEP_TEST_MEDIA", "1")
    assert maintenance.reclaim(tmp_path, tmp_path, failed=False, apply=True) == []


def test_only_actual_fixture_base_is_admitted_and_small_success_media_reclaimed(tmp_path):
    cache = tmp_path / ".cache"
    base = cache / "specific-test-run"
    root = base / "test_example0"
    root.mkdir(parents=True)
    media = root / "short.wav"
    media.write_bytes(b"generated")
    assert not maintenance.safe_root(root, cache)
    assert maintenance.safe_root(root, cache, base)
    assert not maintenance.reclaim(root, cache, failed=True, apply=True, fixture_base=base)
    assert media.exists()
    assert maintenance.reclaim(root, cache, failed=False, apply=True, fixture_base=base)[0][
        "deleted"
    ]
    assert not media.exists()
    active = cache / "worktrees" / "active" / "test_source"
    active.mkdir(parents=True)
    assert not maintenance.safe_root(active, cache, active.parent)


def test_windows_locked_file_is_preserved(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows exclusive handle behavior")
    cache = tmp_path / ".cache"
    root = cache / "pytest-runs/run/tmp/test_locked0"
    root.mkdir(parents=True)
    media = root / "locked.nut"
    media.write_bytes(b"x" * maintenance.LIMIT)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(media), 0x80000000, 0, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        assert not maintenance.reclaim(root, cache, failed=True, apply=True)[0]["deleted"]
        assert media.exists()
    finally:
        kernel.CloseHandle(handle)
    assert maintenance.reclaim(root, cache, failed=True, apply=True)[0]["deleted"]


def test_junction_and_linked_audit_never_touch_external_data(tmp_path):
    cache = tmp_path / ".cache"
    root = cache / "pytest-runs/run/tmp/test_junction0"
    root.mkdir(parents=True)
    outside = tmp_path / "original"
    outside.mkdir()
    original = outside / "original.nut"
    original.write_bytes(b"original" * maintenance.LIMIT)
    link = root / "outside"
    if os.name == "nt":
        command = "New-Item -ItemType Junction -Path '{}' -Target '{}' | Out-Null".format(
            str(link).replace("'", "''"), str(outside).replace("'", "''")
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command], check=True
        )
    else:
        link.symlink_to(outside, target_is_directory=True)
    assert maintenance.reclaim(root, cache, failed=True, apply=True) == []
    assert original.exists()
    audit_source = outside / "original.txt"
    audit_source.write_text("preserve", encoding="utf-8")
    os.link(audit_source, root / "media-reclamation.jsonl")
    own = root / "own.nut"
    own.write_bytes(b"generated")
    assert not maintenance.reclaim(root, cache, failed=False, apply=True)[0]["deleted"]
    assert own.exists() and audit_source.read_text(encoding="utf-8") == "preserve"


def test_manual_relative_traversal_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        maintenance.manual_files(
            tmp_path / ".cache",
            ["pytest-runs/run/tmp/test_x/..\\..\\..\\workspace/user.nut"],
            apply=True,
        )


def test_hook_does_not_request_an_unused_tmp_fixture():
    import conftest

    class Item:
        funcargs = {}

        @property
        def config(self):
            raise AssertionError("No temp factory should be requested")

    hook = conftest.pytest_runtest_teardown(Item(), None)
    next(hook)
    with pytest.raises(StopIteration):
        next(hook)
