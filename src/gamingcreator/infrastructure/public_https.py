"""Bounded, anonymous HTTPS reads from DNS-verified public addresses."""

import hashlib
import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
from concurrent.futures import Future
from contextlib import suppress
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from gamingcreator.infrastructure.rule_sources import html_text

_MAX_BYTES = 2 * 1024 * 1024
_TIMEOUT = 20.0
_REDIRECTS = {301, 302, 303, 307, 308}
_HTML_TYPES = {"text/html", "application/xhtml+xml"}
_DNS_SLOTS = threading.BoundedSemaphore(2)


def public_url(raw: str) -> str:
    if not raw or len(raw) > 2048 or any(c.isspace() or ord(c) < 32 or c == "\\" for c in raw):
        raise ValueError("请输入有效的公开 HTTPS 网页地址。")
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower().removesuffix(".")
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
            or "." not in host
            or len(host) > 253
            or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
                for part in host.split(".")
            )
            or not re.fullmatch(r"[a-z][a-z0-9-]*", host.rsplit(".", 1)[1])
        ):
            raise ValueError
    except (ValueError, UnicodeError) as error:
        raise ValueError("网页须使用公网域名和 HTTPS 标准端口，且无需登录。") from error
    path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
    query = quote(parsed.query, safe="%/:?@!$&'()*+,;=-._~")
    result = urlunsplit(("https", host, path, query, ""))
    if len(result) > 2048:
        raise ValueError("网页地址过长。")
    return result


def _public_address(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    if isinstance(ip, ipaddress.IPv6Address) and (
        ip.ipv4_mapped is not None
        or ip.sixtofour is not None
        or ip.teredo is not None
        or ip.is_site_local
        or ip in ipaddress.IPv6Network("64:ff9b::/96")
    ):
        return False
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def _remaining(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError("网页读取超时。")
    return min(left, 8.0)


def _resolve(host: str, deadline: float) -> list[tuple[int, tuple[Any, ...]]]:
    answer: Future[list[tuple[int, tuple[Any, ...]]]] = Future()
    if not _DNS_SLOTS.acquire(blocking=False):
        raise TimeoutError("网址解析正在处理，请稍后重试。")

    def lookup() -> None:
        try:
            rows = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            answer.set_result(
                list(dict.fromkeys((family, address) for family, _, _, _, address in rows))
            )
        except OSError as error:
            answer.set_exception(error)
        finally:
            _DNS_SLOTS.release()

    try:
        threading.Thread(target=lookup, daemon=True).start()
    except RuntimeError:
        _DNS_SLOTS.release()
        raise
    return answer.result(timeout=_remaining(deadline))


def _connect(host: str, deadline: float) -> socket.socket:
    endpoints = _resolve(host, deadline)
    if not endpoints or any(
        family not in {socket.AF_INET, socket.AF_INET6}
        or not isinstance(address[0], str)
        or not _public_address(address[0])
        for family, address in endpoints
    ):
        raise ValueError("网页重定向或解析到非公网地址。")
    for family, address in endpoints[:8]:
        connection = socket.socket(family, socket.SOCK_STREAM)
        try:
            connection.settimeout(_remaining(deadline))
            connection.connect(address)
        except OSError:
            connection.close()
        else:
            return connection
    raise OSError("无法连接到网页服务器。")


def _response_text(
    response: http.client.HTTPResponse, deadline: float
) -> tuple[bytes, str, str | None]:
    media_type = response.headers.get_content_type()
    if (
        media_type not in _HTML_TYPES | {"text/plain"}
        or response.getheader("Content-Encoding", "identity").lower() != "identity"
    ):
        raise ValueError("网页须直接返回未压缩的 HTML 或纯文本。")
    contents = bytearray()
    while len(contents) <= _MAX_BYTES:
        _remaining(deadline)
        chunk = response.read1(min(65_536, _MAX_BYTES + 1 - len(contents)))
        if not chunk:
            break
        contents.extend(chunk)
    _remaining(deadline)
    if response.length not in (0, None):
        raise ValueError("网页连接提前结束，请重新读取。")
    if not contents or len(contents) > _MAX_BYTES:
        raise ValueError("网页为空或超过 2 MiB。")
    return bytes(contents), media_type, response.headers.get_content_charset()


def _stop(socket_: socket.socket) -> None:
    with suppress(OSError):
        socket_.shutdown(socket.SHUT_RDWR)


def _read(url: str, deadline: float) -> tuple[bytes, str, str | None, str]:
    target = public_url(url)
    tls = ssl.create_default_context()
    for _ in range(4):
        parts = urlsplit(target)
        host = parts.netloc
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        with _connect(host, deadline) as raw:
            raw.settimeout(_remaining(deadline))
            with tls.wrap_socket(raw, server_hostname=host) as verified:
                verified.settimeout(_remaining(deadline))
                connection = http.client.HTTPConnection(host, timeout=_remaining(deadline))
                connection.sock = verified
                connection.auto_open = 0
                timeout = threading.Timer(max(0.0, deadline - time.monotonic()), _stop, (verified,))
                timeout.daemon = True
                timeout.start()
                try:
                    connection.request(
                        "GET",
                        path,
                        headers={
                            "User-Agent": "GamingCreator/1.0",
                            "Accept-Encoding": "identity",
                            "Connection": "close",
                        },
                    )
                    with connection.getresponse() as response:
                        if response.status in _REDIRECTS and (
                            location := response.getheader("Location")
                        ):
                            target = public_url(urljoin(target, location))
                            continue
                        if response.status != 200:
                            raise ValueError(f"网页返回 HTTP {response.status}，需公开可读的正文。")
                        return (*_response_text(response, deadline), target)
                finally:
                    timeout.cancel()
                    connection.close()
    raise ValueError("网页重定向次数过多。")


class _Title(HTMLParser):
    active = False

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self.active = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.active = False

    def handle_data(self, data: str) -> None:
        if self.active:
            self.parts.append(data)


def read_public_page(url: str) -> dict[str, str]:
    try:
        data, media_type, charset, final_url = _read(url, time.monotonic() + _TIMEOUT)
    except (OSError, http.client.HTTPException) as error:
        raise ValueError("无法读取公开网页，请核对地址或改用本地文件。") from error
    encoding = charset if charset in {"utf-8", "gb18030", "gb2312", "gbk", "big5"} else "utf-8-sig"
    try:
        markup = data.decode(encoding)
    except UnicodeDecodeError as error:
        raise ValueError("网页文字编码无法识别。") from error
    title = _Title()
    if media_type in _HTML_TYPES:
        title.feed(markup)
        title.close()
    return {
        "url": final_url,
        "title": " ".join(" ".join(title.parts).split()),
        "text": html_text(markup) if media_type in _HTML_TYPES else markup,
        "retrievedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "responseSha256": hashlib.sha256(data).hexdigest(),
    }
