"""Exercise actual Windows PowerShell launch/reuse/failure lifecycles without a browser."""

import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from contextlib import ExitStack
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop launcher")
LAUNCHER = Path(__file__).resolve().parents[1] / "scripts" / "start-workspace.ps1"
REPOSITORY = Path(sys.executable).resolve().parents[2]


def _command(port, repository=REPOSITORY):
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(LAUNCHER),
        "-NoBrowser",
        "-Port",
        str(port),
        "-Repository",
        str(repository),
    ]


def _environment():
    environment = os.environ.copy()
    environment.update(
        HTTP_PROXY="http://127.0.0.1:1",
        HTTPS_PROXY="http://127.0.0.1:1",
        ALL_PROXY="http://127.0.0.1:1",
        NO_PROXY="",
    )
    return environment


def _run(port, cwd, repository=REPOSITORY, *, use_cmd=False):
    output_path = cwd / f"launcher-{uuid.uuid4().hex}.out"
    error_path = output_path.with_suffix(".err")
    # Real background helpers can inherit pipe handles on Windows; file capture
    # lets the foreground launcher finish without waiting for the server to exit.
    command = _command(port, repository)
    if use_cmd:
        command = [
            "cmd.exe",
            "/d",
            "/c",
            str(LAUNCHER.parents[1] / "Start-Workspace.cmd"),
            "-NoBrowser",
            "-Port",
            str(port),
            "-Repository",
            str(repository),
        ]
    with output_path.open("wb") as stdout, error_path.open("wb") as stderr:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=_environment(),
            stdout=stdout,
            stderr=stderr,
            timeout=40,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        output_path.read_text(encoding="utf-8", errors="replace"),
        error_path.read_text(encoding="utf-8", errors="replace"),
    )


def _health(port):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
        return json.load(response)


@pytest.fixture
def workspace_port():
    if not (REPOSITORY / "scripts" / "env.ps1").is_file():
        pytest.skip("Run lifecycle tests with the repository's isolated .venv Python")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    yield port
    # Stop only a server whose live endpoint still identifies this repository.
    try:
        health = _health(port)
    except OSError:
        return
    if (
        health.get("application") == "gamingcreator-workspace"
        and Path(health.get("repository", "")).resolve() == REPOSITORY
    ):
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"Stop-Process -Id {int(health['pid'])} -Force",
            ],
            capture_output=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=True,
        )


def test_starts_from_other_directory_and_reuses_matching_service(workspace_port, tmp_path):
    first = _run(workspace_port, tmp_path, use_cmd=True)
    assert first.returncode == 0, first.stdout + first.stderr
    health = _health(workspace_port)
    assert health["application"] == "gamingcreator-workspace"
    assert Path(health["repository"]).resolve() == REPOSITORY
    assert health["apiVersion"] == 1
    assert f"PID {health['pid']}" in first.stdout
    state_path = REPOSITORY / ".cache" / "workspace" / f"port-{workspace_port}.json"
    state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    assert state["pid"] == health["pid"]
    assert Path(state["stdout"]).is_file()
    assert Path(state["stderr"]).is_file()
    assert Path(state["stdout"]).parent == REPOSITORY / ".cache" / "workspace"

    again = _run(workspace_port, tmp_path)
    assert again.returncode == 0, again.stdout + again.stderr
    assert "Reusing workspace" in again.stdout
    assert _health(workspace_port)["pid"] == health["pid"]
    assert json.loads(state_path.read_text(encoding="utf-8-sig")) == state


def test_simultaneous_launches_start_only_one_service(workspace_port, tmp_path):
    outputs = []
    with ExitStack() as stack:
        processes = []
        paths = []
        for index in range(2):
            output_path = tmp_path / f"simultaneous-{index}.out"
            error_path = output_path.with_suffix(".err")
            paths.append((output_path, error_path))
            processes.append(
                subprocess.Popen(
                    _command(workspace_port),
                    cwd=tmp_path,
                    env=_environment(),
                    stdout=stack.enter_context(output_path.open("wb")),
                    stderr=stack.enter_context(error_path.open("wb")),
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            )
        try:
            for process, (output_path, error_path) in zip(processes, paths, strict=True):
                process.wait(timeout=40)
                stdout = output_path.read_text(encoding="utf-8", errors="replace")
                stderr = error_path.read_text(encoding="utf-8", errors="replace")
                assert process.returncode == 0, stdout + stderr
                outputs.append(stdout)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
    health = _health(workspace_port)
    assert all(f"PID {health['pid']}" in output for output in outputs)
    assert sum("Workspace ready:" in output for output in outputs) == 1
    assert sum("Reusing workspace:" in output for output in outputs) == 1


def test_foreign_listener_is_reported_and_remains_alive(tmp_path):
    class ForeignService(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = json.dumps(
                {
                    "application": "gamingcreator-workspace",
                    "apiVersion": 1,
                    "repository": str(tmp_path / "different-repository"),
                    "pid": os.getpid(),
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), ForeignService) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            result = _run(port, tmp_path)
            assert result.returncode != 0
            assert "occupied" in result.stderr
            assert "Nothing was stopped" in result.stderr
            assert _health(port)["pid"] == os.getpid()
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_failed_helper_reports_local_logs_and_does_not_write_ready_state(tmp_path):
    repository = _helper_repository(
        tmp_path,
        "import sys\nprint('controlled startup failure', file=sys.stderr)\nsys.exit(7)\n",
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    result = _run(port, tmp_path, repository)
    assert result.returncode != 0
    assert "code 7" in result.stderr
    logs = list((repository / ".cache" / "workspace").glob("*.stderr.log"))
    assert len(logs) == 1
    assert "controlled startup failure" in logs[0].read_text(encoding="utf-8")
    assert not (repository / ".cache" / "workspace" / f"port-{port}.json").exists()


def _helper_repository(tmp_path, source):
    repository = tmp_path / "broken repository with spaces"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(REPOSITORY / "scripts" / "env.ps1", scripts / "env.ps1")
    python_path = repository / ".venv" / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True)
    shutil.copy2(sys.executable, python_path)
    shutil.copy2(REPOSITORY / ".venv" / "pyvenv.cfg", repository / ".venv" / "pyvenv.cfg")
    package = repository / "gamingcreator"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "ui.py").write_text(source, encoding="utf-8")
    return repository


def test_unresponsive_startup_is_bounded_and_its_child_is_stopped(tmp_path):
    repository = _helper_repository(
        tmp_path,
        "import os,time\nfrom pathlib import Path\n"
        "Path('.cache/workspace/controlled-child.pid').write_text(str(os.getpid()))\n"
        "time.sleep(60)\n",
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    started = time.monotonic()
    result = _run(port, tmp_path, repository)
    assert result.returncode != 0
    assert "within 15 seconds" in result.stderr
    assert time.monotonic() - started < 25
    assert not (repository / ".cache" / "workspace" / f"port-{port}.json").exists()
    child_pid = int((repository / ".cache/workspace/controlled-child.pid").read_text())
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, child_pid)
    if handle:
        try:
            exit_code = wintypes.DWORD()
            assert kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            assert exit_code.value != 259, "test-owned venv child was left running"
        finally:
            kernel.CloseHandle(handle)
