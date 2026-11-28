"""Local Studio project locations and Windows video selection."""

import base64
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from threading import Lock

from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.local_paths import is_link, resolve_existing
from gamingcreator.infrastructure.windows_ocr import powershell_executable
from gamingcreator.ui.media_preparation import preparation_project

_PICKER_LOCK = Lock()
_FROZEN_BATCH_FILES = ("source-input.json", "analysis-config.json", "plan.json", "receipt.json")
_PICKER_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
if (-not [Environment]::UserInteractive) { throw 'A Windows desktop is required.' }
$owner = New-Object System.Windows.Forms.Form
$owner.ShowInTaskbar = $false
$owner.FormBorderStyle = 'None'
$owner.Opacity = 0
$owner.TopMost = $true
$owner.Show()
$selected = @()
try {
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = 'Select local videos'
    $dialog.Filter = 'Video files|*.mp4;*.mov;*.mkv;*.webm;*.avi;*.m4v;*.ts;*.mts;*.wmv;*.flv|All files|*.*'
    $dialog.Multiselect = $true
    $dialog.CheckFileExists = $true
    $dialog.RestoreDirectory = $true
    $videos = Join-Path $PWD.Path 'GameVideos'
    if ([IO.Directory]::Exists($videos)) { $dialog.InitialDirectory = $videos }
    if ($dialog.ShowDialog($owner) -eq 'OK') { $selected = @($dialog.FileNames) }
    ConvertTo-Json -InputObject $selected -Compress
} finally {
    if ($null -ne $dialog) { $dialog.Dispose() }
    $owner.Dispose()
}
"""


def _windows_dialog(repository: Path) -> list[str]:
    if os.name != "nt":
        raise AppError("picker.platform", "Windows 工作台支持本机选择器。", ExitCode.ENVIRONMENT)
    if not _PICKER_LOCK.acquire(blocking=False):
        raise AppError("picker.busy", "请先完成或关闭已打开的选择窗口。", ExitCode.INPUT)
    try:
        result = subprocess.run(
            [
                str(powershell_executable()),
                "-NoProfile",
                "-NonInteractive",
                "-Sta",
                "-EncodedCommand",
                base64.b64encode(_PICKER_SCRIPT.encode("utf-16-le")).decode("ascii"),
            ],
            cwd=repository,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=True,
        )
        paths = json.loads(result.stdout)
        if not isinstance(paths, list) or any(type(path) is not str for path in paths):
            raise ValueError("Expected selected paths.")
        return paths
    except subprocess.TimeoutExpired:
        raise AppError("picker.timeout", "选择窗口已超时，请重新打开。", ExitCode.INPUT) from None
    except (OSError, ValueError, subprocess.CalledProcessError):
        raise AppError(
            "picker.unavailable",
            "无法打开 Windows 选择窗口，可手动填写路径。",
            ExitCode.ENVIRONMENT,
        ) from None
    finally:
        _PICKER_LOCK.release()


def studio_local_picker(repository: Path, document: object) -> dict[str, object]:
    if document != {"kind": "videos"}:
        raise ValueError("Expected a local picker kind.")
    paths = _windows_dialog(repository)
    if len(paths) > 100 or any(
        not Path(path).is_absolute() or Path(path).drive.startswith("\\\\") for path in paths
    ):
        raise AppError("picker.videos", "请选择最多 100 段本机录像。", ExitCode.INPUT)
    return {"paths": paths}


def _has_batch_history(project: Path) -> bool:
    directory = project / "media-batches"
    if is_link(directory) or not directory.is_dir():
        return False

    def frozen_batch(batch: Path) -> bool:
        if not re.fullmatch(r"[a-f0-9]{32}", batch.name) or is_link(batch) or not batch.is_dir():
            return False
        try:
            for name in _FROZEN_BATCH_FILES:
                file = batch / name
                info = file.lstat()
                if is_link(file) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    return False
        except OSError:
            return False
        return True

    # Opening the batch catalog checks hashes and state. Browsing only discovers candidates.
    try:
        return any(frozen_batch(batch) for batch in directory.iterdir())
    except OSError:
        return False


def _artifact_directory(repository: Path, folder: str) -> tuple[Path, Path]:
    parts = folder.split("/")
    if (
        parts[0] != "artifacts"
        or len(folder) > 8192
        or any(part in {"", ".", ".."} or any(ch in part for ch in "\\:\0") for part in parts)
    ):
        raise ValueError("Invalid artifact directory.")
    root = resolve_existing(repository)
    target = root.joinpath(*parts)
    resolved = resolve_existing(target)
    if (
        not resolved.is_relative_to(root)
        or resolved.relative_to(root).as_posix() != folder
        or any(
            is_link(path)
            for path in (target, *target.parents)
            if path.is_relative_to(root) and path != root
        )
    ):
        raise ValueError("Invalid artifact directory.")
    return root, resolved


def registered_creation_project(repository: Path, project_id: str) -> Path:
    root, project = _artifact_directory(repository, project_id)
    if (
        preparation_project(root, project_id) != project
        or not (project / "timeline.sqlite3").is_file()
    ):
        raise ValueError("Missing project database.")
    return project


def studio_project_locations(repository: Path, folder: str) -> dict[str, object]:
    try:
        root, target = _artifact_directory(repository, folder)
    except (OSError, ValueError):
        raise AppError(
            "picker.folder", "请选择 artifacts 下的本机工作目录。", ExitCode.INPUT
        ) from None

    def entry(path: Path) -> dict[str, str]:
        return {"path": path.relative_to(root).as_posix(), "name": path.name}

    def valid_project_path(path: Path) -> bool:
        try:
            return preparation_project(root, str(path)) == path
        except AppError:
            return False

    try:
        if folder == "artifacts" and not target.exists():
            return {"folder": folder, "folders": [], "projects": [], "histories": []}
        children = sorted(
            (path for path in target.iterdir() if not is_link(path) and path.is_dir()),
            key=lambda path: (path.name.casefold(), path.name),
        )
        projects = []
        histories = []
        for path in (target, *children):
            if not valid_project_path(path):
                continue
            if (path / "timeline.sqlite3").is_file():
                projects.append(entry(path))
            elif _has_batch_history(path):
                histories.append(entry(path))
    except OSError:
        raise AppError(
            "picker.folder", "请选择 artifacts 下的本机工作目录。", ExitCode.INPUT
        ) from None
    return {
        "folder": entry(target)["path"],
        "folders": [entry(path) for path in children],
        "projects": projects,
        "histories": histories,
    }
