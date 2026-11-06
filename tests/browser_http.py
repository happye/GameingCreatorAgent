"""Bind local test HTTP servers outside Chromium's blocked service-port range."""

from http.server import ThreadingHTTPServer


class BrowserHTTPServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR can let another test bind the same live port.
    allow_reuse_address = False


def browser_server(handler):
    for port in range(20000, 21000):
        try:
            return BrowserHTTPServer(("127.0.0.1", port), handler)
        except OSError as error:
            if (
                error.errno not in (10048, 10013)
                and getattr(error, "winerror", None) not in (10048, 10013)
                and error.errno != 98
            ):
                raise
    raise RuntimeError("No free browser-safe local HTTP port in 20000–20999")
