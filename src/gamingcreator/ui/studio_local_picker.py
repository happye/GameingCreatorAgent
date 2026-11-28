"""Windows file and project folder dialogs for the local Studio."""

import base64
import json
import os
import subprocess
from pathlib import Path
from threading import Lock

from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.windows_ocr import powershell_executable
from gamingcreator.ui.media_preparation import preparation_project

_PICKER_LOCK = Lock()
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
    if ($env:GAMINGCREATOR_PICKER_KIND -eq 'project') {
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.Description = 'Select a project folder under artifacts'
        $dialog.SelectedPath = Join-Path $PWD.Path 'artifacts'
        $dialog.ShowNewFolderButton = $false
        if ($dialog.ShowDialog($owner) -eq 'OK') { $selected = @($dialog.SelectedPath) }
    } else {
        $dialog = New-Object System.Windows.Forms.OpenFileDialog
        $dialog.Title = 'Select local videos'
        $dialog.Filter = 'Video files|*.mp4;*.mov;*.mkv;*.webm;*.avi;*.m4v;*.ts;*.mts;*.wmv;*.flv|All files|*.*'
        $dialog.Multiselect = $true
        $dialog.CheckFileExists = $true
        $dialog.RestoreDirectory = $true
        $videos = Join-Path $PWD.Path 'GameVideos'
        if ([IO.Directory]::Exists($videos)) { $dialog.InitialDirectory = $videos }
        if ($dialog.ShowDialog($owner) -eq 'OK') { $selected = @($dialog.FileNames) }
    }
    ConvertTo-Json -InputObject $selected -Compress
} finally {
    if ($null -ne $dialog) { $dialog.Dispose() }
    $owner.Dispose()
}
"""


def _windows_dialog(repository: Path, kind: str) -> list[str]:
    if os.name != "nt":
        raise AppError("picker.platform", "Windows 工作台支持本机选择器。", ExitCode.ENVIRONMENT)
    if not _PICKER_LOCK.acquire(blocking=False):
        raise AppError("picker.busy", "请先完成或关闭已打开的选择窗口。", ExitCode.INPUT)
    try:
        if kind == "project":
            (repository / "artifacts").mkdir(exist_ok=True)
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
            env={**os.environ, "GAMINGCREATOR_PICKER_KIND": kind},
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
    if (
        not isinstance(document, dict)
        or set(document) != {"kind"}
        or document["kind"] not in ("videos", "project")
    ):
        raise ValueError("Expected a local picker kind.")
    kind = document["kind"]
    paths = _windows_dialog(repository, kind)
    if paths and kind == "project":
        project = preparation_project(repository, paths[0])
        if not project.is_dir():
            raise AppError("picker.folder", "请选择有效的项目目录。", ExitCode.INPUT)
        paths = [project.relative_to(repository.resolve()).as_posix()]
    elif paths and (
        len(paths) > 100
        or any(
            not Path(path).is_absolute() or Path(path).drive.startswith("\\\\") for path in paths
        )
    ):
        raise AppError("picker.videos", "请选择最多 100 段本机录像。", ExitCode.INPUT)
    return {"paths": paths}
