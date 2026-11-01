"""The per-user installer swaps only program parts and never touches the user's data."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/install-app.ps1"

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows installer")


def build(folder: Path, label: str) -> Path:
    runtime = "cpython-fixture"
    files = {
        "toolchain.json": json.dumps(
            {"label": label, "python": {"request": runtime}}, ensure_ascii=False
        ),
        "scripts/helper.ps1": label,
        f".tools/python/{runtime}/runtime.txt": label,
        ".venv/pyvenv.cfg": f"home = C:/old-build/{label}/.tools/python/{runtime}",
        "desktop/bin/GamingCreator.txt": label,
        "docs/references/asr-models.json": "{}",
        "docs/references/asr-native-toolchain.json": "{}",
        "docs/references/embedding-model.json": "{}",
        "models/faster-whisper/.keep": label,
        "models/multilingual-e5-small/.keep": label,
        "licenses/THIRD-PARTY-NOTICES.md": f"# notices {label}\n",
    }
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    marker = {
        "schemaVersion": "gamingcreator-app-v1",
        "builtAt": label,
        "bytes": 100,
        "version": "0.1.0",
        "commit": label,
    }
    (folder / ".gamingcreator-app.json").write_text(json.dumps(marker), encoding="utf-8")
    return folder


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        *arguments,
    ]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def receipt(destination: Path) -> dict:
    return json.loads((destination / ".gamingcreator-install.json").read_text(encoding="utf-8-sig"))


def siblings(destination: Path) -> list[str]:
    return sorted(
        path.name
        for path in destination.parent.iterdir()
        if path.name != destination.name and "." in path.name
    )


def test_install_upgrade_keeps_user_data_and_uninstall_keeps_it_too(tmp_path):
    first = build(tmp_path / "first", "one")
    second = build(tmp_path / "second", "two")
    destination = tmp_path / "apps/GamingCreator"

    result = run("-Source", str(first), "-Destination", str(destination))
    assert result.returncode == 0, result.stderr
    assert (destination / "scripts/helper.ps1").read_text(encoding="utf-8") == "one"
    assert receipt(destination)["upgradedFrom"] is None

    creation = destination / ".cache/workspace/creations/jobs/job.json"
    creation.parent.mkdir(parents=True)
    creation.write_text("mine", encoding="utf-8")
    (destination / "my-project").mkdir()
    (destination / "my-project/notes.txt").write_text("keep", encoding="utf-8")

    result = run("-Source", str(second), "-Destination", str(destination))
    assert result.returncode == 0, result.stderr
    assert (destination / "desktop/bin/GamingCreator.txt").read_text(encoding="utf-8") == "two"
    assert creation.read_text(encoding="utf-8") == "mine"
    assert (destination / "my-project/notes.txt").read_text(encoding="utf-8") == "keep"
    assert receipt(destination)["upgradedFrom"]["builtAt"] == "one"
    assert siblings(destination) == []

    result = run("-Destination", str(destination), "-Uninstall")
    assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in destination.iterdir()) == [
        ".cache",
        ".gamingcreator-data.json",
        "my-project",
    ]
    assert creation.read_text(encoding="utf-8") == "mine"


def test_uninstall_without_data_removes_the_folder(tmp_path):
    destination = tmp_path / "GamingCreator"
    assert (
        run(
            "-Source", str(build(tmp_path / "src", "one")), "-Destination", str(destination)
        ).returncode
        == 0
    )
    result = run("-Destination", str(destination), "-Uninstall")
    assert result.returncode == 0, result.stderr
    assert not destination.exists()


def test_foreign_folder_and_incomplete_source_change_nothing(tmp_path):
    foreign = tmp_path / "Other"
    foreign.mkdir()
    (foreign / "file.txt").write_text("x", encoding="utf-8")
    source = build(tmp_path / "src", "one")
    result = run("-Source", str(source), "-Destination", str(foreign))
    assert result.returncode != 0 and "not empty" in result.stderr
    assert sorted(path.name for path in foreign.iterdir()) == ["file.txt"]

    (source / ".venv/pyvenv.cfg").unlink()
    (source / ".venv").rmdir()
    destination = tmp_path / "GamingCreator"
    result = run("-Source", str(source), "-Destination", str(destination))
    assert result.returncode != 0 and ".venv is missing" in result.stderr
    assert not destination.exists()
    assert run("-Destination", str(foreign), "-Uninstall").returncode != 0


def test_failed_swap_restores_the_previous_program(tmp_path):
    destination = tmp_path / "GamingCreator"
    assert (
        run(
            "-Source", str(build(tmp_path / "first", "one")), "-Destination", str(destination)
        ).returncode
        == 0
    )
    # An open file inside desktop/ blocks moving that folder midway through the swap.
    with open(destination / "desktop/bin/GamingCreator.txt", encoding="utf-8"):
        result = run(
            "-Source", str(build(tmp_path / "second", "two")), "-Destination", str(destination)
        )
    assert result.returncode != 0
    for name in (
        "toolchain.json",
        "scripts/helper.ps1",
        "desktop/bin/GamingCreator.txt",
    ):
        assert "one" in (destination / name).read_text(encoding="utf-8"), name
    cfg = (destination / ".venv/pyvenv.cfg").read_text(encoding="utf-8")
    assert f"home = {destination.resolve() / '.tools/python/cpython-fixture'}" in cfg
    assert receipt(destination)["builtAt"] == "one"
    assert siblings(destination) == []


def test_uninstall_with_a_file_in_use_removes_nothing(tmp_path):
    destination = tmp_path / "GamingCreator"
    assert (
        run(
            "-Source", str(build(tmp_path / "src", "one")), "-Destination", str(destination)
        ).returncode
        == 0
    )
    with open(destination / "desktop/bin/GamingCreator.txt", encoding="utf-8"):
        result = run("-Destination", str(destination), "-Uninstall")
    assert result.returncode != 0
    assert (destination / "scripts/helper.ps1").read_text(encoding="utf-8") == "one"
    assert (destination / ".gamingcreator-app.json").exists()
    assert siblings(destination) == []


def test_reinstall_after_a_data_keeping_uninstall_reuses_the_data(tmp_path):
    destination = tmp_path / "GamingCreator"
    source = build(tmp_path / "src", "one")
    assert run("-Source", str(source), "-Destination", str(destination)).returncode == 0
    (destination / ".cache").mkdir()
    (destination / ".cache/mine.json").write_text("keep", encoding="utf-8")
    assert run("-Destination", str(destination), "-Uninstall").returncode == 0
    result = run("-Source", str(source), "-Destination", str(destination))
    assert result.returncode == 0, result.stderr
    assert (destination / ".cache/mine.json").read_text(encoding="utf-8") == "keep"
    assert not (destination / ".gamingcreator-data.json").exists()
    assert (destination / "scripts/helper.ps1").exists()


def test_relative_destination_uses_the_powershell_location(tmp_path):
    source = build(tmp_path / "src", "one")
    work = tmp_path / "work"
    work.mkdir()
    command = (
        f"Set-Location -LiteralPath '{work}'; & '{SCRIPT}' -Source '{source}' -Destination .\\app"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert (work / "app/scripts/helper.ps1").exists()


def test_an_unfinished_build_is_never_installed(tmp_path):
    source = build(tmp_path / "src", "one")
    (source / ".gamingcreator-app.json").write_text(
        json.dumps({"schemaVersion": "gamingcreator-app-v1", "incomplete": True}), encoding="utf-8"
    )
    destination = tmp_path / "GamingCreator"
    result = run("-Source", str(source), "-Destination", str(destination))
    assert result.returncode != 0 and "unfinished build" in result.stderr
    assert not destination.exists()


def test_install_retargets_pyvenv_home_to_destination_runtime(tmp_path):
    source = build(tmp_path / "src", "one")
    destination = tmp_path / "GamingCreator"
    result = run("-Source", str(source), "-Destination", str(destination))
    assert result.returncode == 0, result.stderr
    cfg = (destination / ".venv/pyvenv.cfg").read_text(encoding="utf-8")
    expected = str((destination / ".tools/python/cpython-fixture").resolve())
    assert f"home = {expected}" in cfg
    assert "C:/old-build/" not in cfg
