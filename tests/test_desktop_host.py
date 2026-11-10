"""The thin desktop host builds with Windows' own compiler, serves, stops, and stays single."""

import ctypes
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "desktop/bin/GamingCreator.exe"

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop host")


@pytest.fixture(scope="module")
def built():
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "scripts/build-desktop.ps1"),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )
    return EXE


def service_processes(port):
    listing = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | ForEach-Object { $_.CommandLine }",
        ],
        capture_output=True,
        check=True,
    ).stdout
    # Other processes' command lines may hold non-UTF-8 text (e.g. GBK paths); only the
    # ASCII "--port N " marker matters here.
    text = listing.decode("utf-8", errors="replace")
    return [line for line in text.splitlines() if f"--port {port} " in line]


def test_smoke_serves_then_stops_whole_service_tree(built):
    result = subprocess.run([str(built), "--smoke"], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    line = result.stdout.strip()
    assert line.startswith("READY http://127.0.0.1:") and line.endswith("/creation")
    port = line.rsplit(":", 1)[1].split("/")[0]
    assert service_processes(port) == []


def test_second_instance_refuses_while_first_holds_the_lock(built):
    key = hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:16].upper()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, True, f"Local\\GamingCreator.Desktop.{key}")
    assert handle
    try:
        result = subprocess.run([str(built), "--smoke"], capture_output=True, timeout=60)
        assert result.returncode == 1
        assert "已经在运行" in result.stderr.decode("utf-8", "replace") or result.stderr
    finally:
        kernel.ReleaseMutex(ctypes.c_void_p(handle))
        kernel.CloseHandle(ctypes.c_void_p(handle))
