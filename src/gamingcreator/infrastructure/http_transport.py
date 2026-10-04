"""Bounded, cancellable HTTPS transport with no inherited proxies or credentials."""

import os
from dataclasses import dataclass, field
from math import isfinite
from typing import Protocol

import httpx

DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
MAX_RESPONSE_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: bytes = field(repr=False)


class TransportError(Exception):
    def __init__(self, code: str, retryable: bool = False) -> None:
        allowed = {
            "provider.auth",
            "provider.network",
            "provider.response_limit",
            "provider.transport",
            "provider.cancelled",
            "provider.timeout",
        }
        if code not in allowed:
            raise ValueError("Unknown transport error code.")
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class VisionTransport(Protocol):
    async def post(self, payload: dict[str, object], timeout_seconds: float) -> HttpResponse: ...


class HttpxVisionTransport:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def post(self, payload: dict[str, object], timeout_seconds: float) -> HttpResponse:
        if (
            isinstance(timeout_seconds, bool)
            or not isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise TransportError("provider.timeout")
        # Resolve only in the sending process; never put this value in records or exceptions.
        credential = os.environ.get("DEEPSEEK_API_KEY")
        if not credential or not credential.strip() or any(c in credential for c in "\r\n"):
            raise TransportError("provider.auth")
        try:
            async with httpx.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                transport=self._transport,
                timeout=httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds)),
                headers={
                    "Authorization": "Bearer " + credential,
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                },
            ) as client:
                async with client.stream("POST", DEEPSEEK_ENDPOINT, json=payload) as response:
                    if response.status_code != 200:
                        return HttpResponse(response.status_code, b"")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise TransportError("provider.response_limit")
                    length = response.headers.get("content-length")
                    if length is not None:
                        try:
                            oversized = int(length) > MAX_RESPONSE_BYTES
                        except ValueError:
                            raise TransportError("provider.transport") from None
                        if oversized:
                            raise TransportError("provider.response_limit")
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=65_536):
                        if len(chunks) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise TransportError("provider.response_limit")
                        chunks.extend(chunk)
                    return HttpResponse(response.status_code, bytes(chunks))
        except httpx.RequestError:
            raise TransportError("provider.network", retryable=True) from None
        except (ValueError, UnicodeError):
            raise TransportError("provider.transport") from None
