"""The music catalog is metadata-only and read-only."""

import json
import threading
from urllib.request import urlopen

from test_creation_jobs import service  # noqa: F401

from gamingcreator.ui.server import create_server


def test_music_http_empty_catalog(service):  # noqa: F811
    server = create_server("127.0.0.1", 0, service.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/api/creation/music") as response:
            data = json.load(response)
        assert data == {"tracks": [], "issues": []}
        assert not (service.repository / ".cache/workspace/music").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
