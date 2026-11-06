"""Bind local test HTTP servers outside Chromium's blocked service-port range."""

from http.server import ThreadingHTTPServer


def browser_server(handler):
    for port in range(20000, 21000):
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), handler)
        except OSError as error:
            if (
                error.errno != 10048
                and getattr(error, "winerror", None) != 10048
                and error.errno != 98
            ):
                raise
    raise RuntimeError("No free browser-safe local HTTP port in 20000–20999")
