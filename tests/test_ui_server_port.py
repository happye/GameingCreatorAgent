"""A random port that Chromium refuses (ERR_UNSAFE_PORT) is never handed to the browser."""

from gamingcreator.ui import server


def test_random_port_skips_chromium_unsafe_ports(tmp_path, monkeypatch):
    original = server.WorkspaceServer
    made = []

    class FirstUnsafe(original):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not made:
                self.server_port = 1720  # as handed out on a 1024+ dynamic range
            made.append(self)

    monkeypatch.setattr(server, "WorkspaceServer", FirstUnsafe)
    created = server.create_server("127.0.0.1", 0, tmp_path)
    try:
        assert len(made) == 2 and created is made[1]
        assert created.server_port not in server.CHROMIUM_UNSAFE_PORTS
        assert made[0].socket.fileno() == -1  # the refused one was closed
    finally:
        created.server_close()


def test_explicit_port_is_never_changed(tmp_path):
    created = server.create_server("127.0.0.1", 0, tmp_path)
    port = created.server_port
    created.server_close()
    again = server.create_server("127.0.0.1", port, tmp_path)
    try:
        assert again.server_port == port
    finally:
        again.server_close()
