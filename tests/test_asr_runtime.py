import hashlib
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from gamingcreator.application.asr import ModelFile
from gamingcreator.infrastructure import asr_runtime


@pytest.fixture
def bundle(tmp_path: Path) -> tuple[Path, Path, tuple[ModelFile, ...]]:
    repository = tmp_path / "repository"
    native = repository / ".tools" / "native"
    native.mkdir(parents=True)
    files = []
    for name in sorted(asr_runtime.NATIVE_FILES):
        content = name.encode("ascii")
        (native / name).write_bytes(content)
        files.append(ModelFile(name, len(content), hashlib.sha256(content).hexdigest()))
    return repository, native, tuple(files)


def test_complete_pinned_bundle_is_valid(
    bundle: tuple[Path, Path, tuple[ModelFile, ...]],
) -> None:
    repository, native, files = bundle
    asr_runtime.verify_native(native, files, repository)


@pytest.mark.parametrize("operation", ["missing", "same_size_modified", "wrong_size"])
def test_incomplete_or_modified_runtime_fails(
    bundle: tuple[Path, Path, tuple[ModelFile, ...]], operation: str
) -> None:
    repository, native, files = bundle
    target = native / files[0].name
    if operation == "missing":
        target.unlink()
    else:
        target.write_bytes(b"x" * (files[0].size if operation == "same_size_modified" else 1))
    with pytest.raises((ValueError, OSError)):
        asr_runtime.verify_native(native, files, repository)


@pytest.mark.parametrize("operation", ["missing", "duplicate", "unknown", "traversal"])
def test_manifest_requires_exact_whitelist(
    bundle: tuple[Path, Path, tuple[ModelFile, ...]], operation: str
) -> None:
    repository, native, files = bundle
    if operation == "missing":
        files = files[:-1]
    elif operation == "duplicate":
        files = (*files[:-1], files[0])
    else:
        name = "untrusted.dll" if operation == "unknown" else "../msvcp140.dll"
        files = (replace(files[0], name=name), *files[1:])
    with pytest.raises(ValueError, match="configuration"):
        asr_runtime.verify_native(native, files, repository)


@pytest.mark.parametrize("size,sha256", [(True, "a" * 64), (0, "a" * 64), (1, "not-a-hash")])
def test_manifest_rejects_invalid_sizes_and_hashes(
    bundle: tuple[Path, Path, tuple[ModelFile, ...]], size: int, sha256: str
) -> None:
    repository, native, files = bundle
    files = (replace(files[0], size=size, sha256=sha256), *files[1:])
    with pytest.raises(ValueError, match="configuration"):
        asr_runtime.verify_native(native, files, repository)


def test_native_directory_outside_repository_is_rejected(
    bundle: tuple[Path, Path, tuple[ModelFile, ...]],
) -> None:
    repository, native, files = bundle
    with pytest.raises(ValueError, match="configuration"):
        asr_runtime.verify_native(native, files, repository / "other")


def test_runtime_audit_recognizes_renamed_numpy_crt_and_ignores_system_os_libraries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    crt = root / "MSVCP140-4fa28f11.dll"
    crt.write_bytes(b"numpy-crt")
    monkeypatch.setattr(
        asr_runtime,
        "_runtime_module_paths",
        lambda: [crt, tmp_path / "kernel32.dll", crt],
    )
    assert asr_runtime.loaded_runtime_libraries(root) == [
        {
            "name": crt.name,
            "path": str(crt.resolve()),
            "sha256": hashlib.sha256(b"numpy-crt").hexdigest(),
        }
    ]


def test_runtime_audit_rejects_external_crt_before_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    monkeypatch.setattr(
        asr_runtime, "_runtime_module_paths", lambda: [tmp_path / "vcruntime140_1.dll"]
    )
    with pytest.raises(ValueError, match="outside"):
        asr_runtime.loaded_runtime_libraries(root)


def test_current_windows_runtime_libraries_are_project_local() -> None:
    if sys.platform != "win32":
        assert asr_runtime._runtime_module_paths() == []
        return
    # A worker worktree shares the outer repository's isolated interpreter.
    roots = [
        parent
        for parent in Path(sys.executable).resolve().parents
        if (parent / "toolchain.json").is_file() and (parent / ".tools" / "python").is_dir()
    ]
    assert roots, "Run this check with the project's isolated Python."
    libraries = asr_runtime.loaded_runtime_libraries(roots[0])
    assert libraries
    assert all(Path(item["path"]).is_absolute() and len(item["sha256"]) == 64 for item in libraries)
