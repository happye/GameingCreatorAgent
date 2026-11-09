"""Runtime source identity and immutable server startup snapshots."""

import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import urllib.request
from contextlib import ExitStack

import pytest

from gamingcreator.ui import server as server_module
from gamingcreator.ui.runtime_identity import runtime_identity


def test_studio_module_connection_burst_survives_delayed_accept(tmp_path):
    """Module connections may queue while the server thread is busy scheduling handlers."""
    paths = [path for path in server_module.ASSETS if path.startswith("/assets/studio/")]
    assert len(paths) > 5
    with server_module.create_server("127.0.0.1", 0, tmp_path) as server, ExitStack() as peers:
        connections = [
            peers.enter_context(socket.create_connection(server.server_address, timeout=2))
            for _ in paths
        ]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for peer, path in zip(connections, paths, strict=True):
                peer.sendall(f"GET {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode())
            for peer in connections:
                with http.client.HTTPResponse(peer) as response:
                    response.begin()
                    assert response.status == 200
                    assert response.read()
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.mark.parametrize("suffix", [".py", ".js", ".css", ".json", ".txt", ".html"])
def test_identity_changes_with_source_bytes(tmp_path, suffix):
    source = tmp_path / ("source" + suffix)
    source.write_text("before")
    original = runtime_identity(tmp_path)
    source.write_text("after")
    assert runtime_identity(tmp_path)["sha256"] != original["sha256"]


def test_identity_excludes_caches_secrets_and_media_and_binds_root(tmp_path):
    root = tmp_path / "package"
    root.mkdir()
    (root / "source.py").write_text("source")
    original = runtime_identity(root)
    for name in [".env", "clip.mp4", "source.pyc", "__pycache__/cached.py"]:
        path = root / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("ignored")
    assert runtime_identity(root) == original
    other = tmp_path / "other"
    other.mkdir()
    (other / "source.py").write_text("source")
    identity = runtime_identity(other)
    assert identity["sha256"] == original["sha256"]
    assert identity["packageRoot"] != original["packageRoot"]


def test_health_freezes_startup_identity_after_source_changes(tmp_path, monkeypatch):
    package = tmp_path / "gamingcreator"
    package.mkdir()
    source = package / "backend.py"
    source.write_text("before")
    asset = package / "frontend.js"
    asset.write_text("before")
    expected = runtime_identity(package)
    monkeypatch.setattr(server_module, "runtime_identity", lambda _: runtime_identity(package))
    with server_module.create_server("127.0.0.1", 0, tmp_path) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for changed in [source, asset]:
                changed.write_text("after")
                assert runtime_identity(package) != expected
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{server.server_port}/api/health"
                ) as response:
                    assert json.load(response)["runtimeIdentity"] == expected
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS directory junction regression")
def test_identity_prunes_external_and_loop_junctions(tmp_path):
    root = tmp_path / "package"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "source.py").write_text("source")
    external = outside / "synthetic.json"
    external.write_text("fixture0")
    expected = runtime_identity(root)
    links = []
    try:
        for link, target in [(root / "linked-data", outside), (root / "loop", root)]:
            subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                check=True,
                capture_output=True,
                timeout=10,
            )
            links.append(link)
            assert link.is_junction()
        assert runtime_identity(root) == expected
        external.write_text("fixture1")
        assert runtime_identity(root) == expected
        # A package reached through an ancestor junction is still a valid root.
        assert runtime_identity(root / "loop") == expected
    finally:
        # Remove only the junction entries; never recursively delete their targets.
        for link in reversed(links):
            os.rmdir(link)
    assert external.read_text() == "fixture1"
    assert (root / "source.py").is_file()
