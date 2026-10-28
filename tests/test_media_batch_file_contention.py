"""Batch checkpoints tolerate bounded real cross-process Windows file sharing."""

import asyncio
import copy
import os
import time
from pathlib import Path

import pytest
from test_benchmark_workflow_file_contention import held
from test_media_batch import batch  # noqa: F401 - shared offline preparation fixture

from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.media_batch_files import MediaBatchFiles


@pytest.fixture
def saved_batch(request):
    project, _, _, media, execute = request.getfixturevalue("batch")
    result = asyncio.run(execute())
    files = MediaBatchFiles(project, result["batchId"])
    files.acquire()
    try:
        plan, state, digest = files.load()
        frozen = {path.name: path.read_bytes() for path in files.directory.glob("*.json")}
        original_preparations = list(media.extractions)
        yield files, plan, state, digest, frozen, media, original_preparations
    finally:
        files.close()


@pytest.mark.skipif(os.name != "nt", reason="Real Windows sharing semantics")
@pytest.mark.parametrize("reading", [True, False])
@pytest.mark.parametrize("release", [True, False])
def test_batch_state_sharing_release_or_timeout_keeps_identity_and_outputs(
    saved_batch, reading, release
):
    files, plan, state, digest, frozen, media, preparations = saved_batch
    outputs = {
        item: item.read_bytes()
        for item in files.project.rglob("*")
        if item.is_file()
        and not item.is_relative_to(files.directory)
        and not item.name.endswith(".lock")
    }
    assert outputs
    path = files.directory / "state.json"
    other = files.directory / ".state-other-writer.tmp"
    other.write_bytes(b"other writer")
    changed = copy.deepcopy(state)
    changed["items"][0]["message"] = "checkpoint marker"
    with held(path, 0 if reading else 1, release_after=0.2 if release else None):
        start = time.monotonic()
        if release:
            if reading:
                assert files.load() == (plan, state, digest)
            else:
                files.save(changed, plan, digest)
        elif reading:
            with pytest.raises(PermissionError):
                files.load()
        else:
            with pytest.raises(AppError) as raised:
                files.save(changed, plan, digest)
            assert raised.value.code == "storage.batch_checkpoint"
            assert raised.value.exit_code == ExitCode.STORAGE
        assert (0.15 if release else 0.9) <= time.monotonic() - start < 2
    loaded_plan, loaded_state, loaded_digest = files.load()
    assert loaded_plan == plan and loaded_digest == digest
    assert loaded_state == (changed if release and not reading else state)
    for name, data in frozen.items():
        if name != "state.json" or not release or reading:
            assert (files.directory / name).read_bytes() == data
    assert list(files.directory.glob("*.tmp")) == [other]
    assert other.read_bytes() == b"other writer"
    assert media.extractions == preparations
    assert all(item.read_bytes() == data for item, data in outputs.items())
    assert [item["runId"] for item in loaded_state["items"]] == [item.run_id for item in plan.items]


@pytest.mark.parametrize("reading", [True, False])
def test_nonsharing_batch_errors_do_not_retry(saved_batch, monkeypatch, reading):
    import gamingcreator.infrastructure.media_batch_files as module

    files, plan, state, digest, frozen, _, _ = saved_batch
    attempts, sleeps = [], []
    error = OSError(2, "missing")
    original_read = module.read_batch_bytes

    def fail_replace(*_):
        attempts.append(True)
        raise error

    def fail_read(path):
        if path.name == "state.json":
            attempts.append(True)
            raise error
        return original_read(path)

    monkeypatch.setattr("gamingcreator.infrastructure.file_sharing.time.sleep", sleeps.append)
    if reading:
        monkeypatch.setattr(module, "read_batch_bytes", fail_read)
        with pytest.raises(OSError) as raised:
            files.load()
        assert raised.value is error
    else:
        monkeypatch.setattr(Path, "replace", fail_replace)
        with pytest.raises(AppError) as raised:
            files.save(state, plan, digest)
        assert raised.value.code == "storage.batch_checkpoint"
    assert attempts == [True] and sleeps == []
    assert (files.directory / "state.json").read_bytes() == frozen["state.json"]
    assert not list(files.directory.glob("*.tmp"))


@pytest.mark.parametrize("reading", [True, False])
def test_batch_wait_revalidates_paths_before_retry(saved_batch, monkeypatch, reading):
    import gamingcreator.infrastructure.media_batch_files as module

    files, plan, state, digest, frozen, _, _ = saved_batch
    checked, operations = [], []
    original_check = module._plain_state
    original_read = module.read_batch_bytes
    sharing = OSError("sharing")
    sharing.winerror = 32

    def check(path):
        if path.name == "state.json":
            checked.append(path)
            if operations:
                raise ValueError("changed link")
        return original_check(path)

    def fail_read(path):
        if path.name == "state.json":
            operations.append(True)
            raise sharing
        return original_read(path)

    def fail_replace(*_):
        operations.append(True)
        raise sharing

    monkeypatch.setattr(module, "_plain_state", check)
    monkeypatch.setattr("gamingcreator.infrastructure.file_sharing.time.sleep", lambda _: None)
    if reading:
        monkeypatch.setattr(module, "read_batch_bytes", fail_read)
        with pytest.raises(ValueError, match="changed link"):
            files.load()
    else:
        monkeypatch.setattr(Path, "replace", fail_replace)
        with pytest.raises(AppError) as raised:
            files.save(state, plan, digest)
        assert raised.value.code == "storage.batch_checkpoint"
    assert len(checked) >= 2 and operations == [True]
    assert (files.directory / "state.json").read_bytes() == frozen["state.json"]
    assert not list(files.directory.glob("*.tmp"))
