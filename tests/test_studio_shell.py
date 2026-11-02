"""Studio workbench shell: served modules, vendored library integrity, CSP-compatible page."""

import hashlib
import json
import re
import threading
from pathlib import Path
from urllib.request import urlopen

import pytest

from gamingcreator.ui.server import ASSETS, create_server

STATIC = Path(__file__).resolve().parents[1] / "src/gamingcreator/ui/static"


def test_vendored_modules_match_their_recorded_hashes():
    manifest = json.loads((STATIC / "vendor/vendor.json").read_text(encoding="utf-8"))
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((STATIC / "vendor" / name).read_bytes()).hexdigest() == digest
    # Every module import stays relative, so no inline import map is needed.
    for path in [*STATIC.glob("vendor/*.js"), *STATIC.glob("studio/*.js")]:
        text = path.read_text(encoding="utf-8")
        for specifier in re.findall(r'(?:from|import)\s*"([^"]+)"', text):
            assert specifier.startswith(("./", "../")), (path.name, specifier)


def test_studio_page_has_no_inline_script():
    page = (STATIC / "studio.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script([^>]*)>(.*?)</script>", page, re.S)
    assert scripts and all('src="' in attrs and not body.strip() for attrs, body in scripts)


@pytest.fixture
def server(tmp_path):
    instance = create_server("127.0.0.1", 0, tmp_path)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{instance.server_port}"
    finally:
        instance.shutdown()
        instance.server_close()


def test_studio_routes_are_served_with_module_types(server):
    studio_paths = [p for p in ASSETS if p == "/studio" or "/studio" in p or "/vendor/" in p]
    # Every studio module on disk must be routed, or the page fails to load it.
    modules = {f"/assets/studio/{p.name}" for p in STATIC.glob("studio/*.js")}
    assert modules <= set(studio_paths)
    for path in studio_paths:
        with urlopen(server + path, timeout=10) as response:
            assert response.status == 200
            kind = response.headers["Content-Type"]
            assert kind.startswith(
                "text/html"
                if path == "/studio"
                else ("text/css" if path.endswith(".css") else "text/javascript")
            )
            assert "script-src 'self'" in response.headers["Content-Security-Policy"]
