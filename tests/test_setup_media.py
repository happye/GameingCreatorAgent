"""Public offline media setup preserves pins and refuses replacement or path escape."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NAMES = [
    item["path"]
    for item in json.loads((ROOT / "docs/references/media-toolchain.json").read_text())["files"]
]
SHELLS = [shell for shell in ("pwsh", "powershell") if shutil.which(shell)]


@pytest.fixture
def media_repo(tmp_path):
    repo, source = tmp_path / "repo", tmp_path / "source"
    (repo / "scripts").mkdir(parents=True)
    (repo / "docs/references").mkdir(parents=True)
    source.mkdir()
    for name in ("toolchain.ps1", "setup-media.ps1"):
        shutil.copyfile(ROOT / "scripts" / name, repo / "scripts" / name)
    files = []
    for name in NAMES:
        data = ("fake pinned file " + name).encode()
        (source / name).write_bytes(data)
        files.append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {"schemaVersion": 1, "files": files}
    (repo / "docs/references/media-toolchain.json").write_text(json.dumps(manifest))
    return repo, source, manifest


def shell_env():
    env = os.environ.copy()
    env.pop("PSMODULEPATH", None)  # Let each PowerShell edition choose its own modules.
    return env


def invoke(repo, source, shell):
    return subprocess.run(
        [
            shell,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(repo / "scripts/setup-media.ps1"),
            "-SourceBin",
            str(source),
        ],
        capture_output=True,
        env=shell_env(),
        text=True,
        timeout=30,
    )


def snapshot(path):
    return {item.relative_to(path): item.read_bytes() for item in path.rglob("*") if item.is_file()}


@pytest.mark.parametrize("shell", SHELLS)
def test_public_setup_and_matching_install_are_idempotent(media_repo, shell):
    repo, source, _ = media_repo
    before = snapshot(source)
    assert invoke(repo, source, shell).returncode == 0
    assert snapshot(repo / ".tools/ffmpeg/bin") == before == snapshot(source)
    assert invoke(repo, source, shell).returncode == 0
    assert not list((repo / ".tools").glob(".media-stage-*"))
    checker = repo / "scripts/check-media.ps1"
    checker.write_text(
        "param($Root)\n. (Join-Path $PSScriptRoot 'toolchain.ps1')\nAssert-ProjectMediaTools $Root"
    )
    check = subprocess.run(
        [shell, "-NoProfile", "-File", str(checker), str(repo)], capture_output=True
    )
    assert check.returncode == 0, check.stderr
    assert snapshot(source) == before


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize(
    "damage", ["missing", "hash", "existing", "escape", "duplicate", "empty", "sha"]
)
def test_invalid_source_manifest_or_existing_install_never_changes_bytes(media_repo, shell, damage):
    repo, source, manifest = media_repo
    if damage == "missing":
        (source / NAMES[0]).unlink()
    elif damage == "hash":
        (source / NAMES[0]).write_bytes(b"bad")
    elif damage == "existing":
        target = repo / ".tools/ffmpeg/bin"
        target.mkdir(parents=True)
        (target / "keep.txt").write_bytes(b"existing installation")
    else:
        if damage == "escape":
            manifest["files"][0]["path"] = "../escape.dll"
        elif damage == "duplicate":
            manifest["files"][1] = manifest["files"][0]
        elif damage == "empty":
            manifest["files"] = []
        elif damage == "sha":
            manifest["files"][0]["sha256"] = "bad"
        (repo / "docs/references/media-toolchain.json").write_text(json.dumps(manifest))
    before_source = snapshot(source)
    before_tools = snapshot(repo / ".tools")
    assert invoke(repo, source, shell).returncode != 0
    assert snapshot(source) == before_source
    assert snapshot(repo / ".tools") == before_tools
    assert not list((repo / ".tools").glob(".media-stage-*"))


@pytest.mark.parametrize("shell", SHELLS)
def test_concurrent_publish_never_merges_or_overwrites(media_repo, shell):
    repo, source, _ = media_repo
    command = [
        shell,
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(repo / "scripts/setup-media.ps1"),
        "-SourceBin",
        str(source),
    ]
    jobs = [
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=shell_env())
        for _ in range(2)
    ]
    for job in jobs:
        job.communicate(timeout=30)
    assert any(job.returncode == 0 for job in jobs)
    assert snapshot(repo / ".tools/ffmpeg/bin") == snapshot(source)
    assert not list((repo / ".tools").glob(".media-stage-*"))


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("linked", ["source", "target", "tools", "source-file"])
def test_reparse_paths_are_refused(media_repo, tmp_path, shell, linked):
    repo, source, _ = media_repo
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_bytes(b"preserve")
    if linked == "source":
        link, original = tmp_path / "linked-source", source
        source = link
    elif linked == "target":
        (repo / ".tools").mkdir()
        link, original = repo / ".tools/ffmpeg", outside
    elif linked == "tools":
        link, original = repo / ".tools", outside
    else:
        link, original = source / NAMES[0], outside / "keep"
        link.unlink()
    if linked == "source-file":
        try:
            link.symlink_to(original)
        except OSError:
            pytest.skip("File symlink privilege unavailable")
    else:
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(original)], check=True, capture_output=True
        )
    try:
        assert invoke(repo, source, shell).returncode != 0
        assert (outside / "keep").read_bytes() == b"preserve"
    finally:
        if link.is_symlink():
            link.unlink()
        else:
            os.rmdir(link)


@pytest.mark.parametrize("shell", SHELLS)
def test_staged_hash_failure_cleans_only_owned_stage(media_repo, shell):
    repo, source, _ = media_repo
    tools = repo / ".tools"
    other = tools / ".media-stage-other"
    other.mkdir(parents=True)
    (other / "keep.txt").write_bytes(b"keep")
    script = repo / "scripts/toolchain.ps1"
    code = script.read_text(encoding="utf-8")
    escaped_source = str(source).replace("'", "''")
    escaped_file = str(source / NAMES[0]).replace("'", "''")
    hook = f"  if ($BinaryRoot -eq '{escaped_source}') {{ [IO.File]::WriteAllText('{escaped_file}', 'changed after validation') }}\n"
    code = code.replace(
        "}\n\nfunction Assert-ProjectMediaTools", hook + "}\n\nfunction Assert-ProjectMediaTools"
    )
    script.write_text(code, encoding="utf-8")
    assert invoke(repo, source, shell).returncode != 0
    assert not (tools / "ffmpeg").exists()
    assert list(tools.iterdir()) == [other]
    assert (other / "keep.txt").read_bytes() == b"keep"
