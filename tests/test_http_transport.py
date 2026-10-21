"""Offline contract: bounded HTTP bodies are kept for non-200 provider replies."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from gamingcreator.infrastructure.http_transport import (
    DEEPSEEK_ENDPOINT,
    MAX_RESPONSE_BYTES,
    HttpxVisionTransport,
    TransportError,
)


def _handler(status: int, body: bytes, *, content_length: str | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == DEEPSEEK_ENDPOINT
        assert request.method == "POST"
        assert request.headers.get("Authorization", "").startswith("Bearer ")
        assert request.headers.get("Accept-Encoding") == "identity"
        headers = {"content-encoding": "identity"}
        if content_length is not None:
            headers["content-length"] = content_length
        return httpx.Response(status, content=body, headers=headers)

    return handler


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    yield
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def test_non_200_keeps_bounded_error_body(api_key):
    payload = {"error": {"message": "invalid json mode request", "type": "invalid_request_error"}}
    body = json.dumps(payload).encode("utf-8")
    transport = HttpxVisionTransport(transport=httpx.MockTransport(_handler(400, body)))

    async def scenario():
        response = await transport.post({"model": "deepseek-flash"}, 5.0)
        assert response.status_code == 400
        assert response.body == body

    asyncio.run(scenario())


def test_200_still_returns_body(api_key):
    body = b'{"ok":true}'
    transport = HttpxVisionTransport(transport=httpx.MockTransport(_handler(200, body)))

    async def scenario():
        response = await transport.post({"model": "deepseek-flash"}, 5.0)
        assert response.status_code == 200
        assert response.body == body

    asyncio.run(scenario())


def test_oversized_error_body_is_refused(api_key):
    transport = HttpxVisionTransport(
        transport=httpx.MockTransport(
            _handler(400, b"x", content_length=str(MAX_RESPONSE_BYTES + 1))
        )
    )

    async def scenario():
        with pytest.raises(TransportError) as refused:
            await transport.post({"model": "deepseek-flash"}, 5.0)
        assert refused.value.code == "provider.response_limit"

    asyncio.run(scenario())


def test_missing_api_key_refuses_before_network(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    transport = HttpxVisionTransport(transport=httpx.MockTransport(_handler(200, b"{}")))

    async def scenario():
        with pytest.raises(TransportError) as refused:
            await transport.post({"model": "deepseek-flash"}, 5.0)
        assert refused.value.code == "provider.auth"

    asyncio.run(scenario())


def test_invalid_timeout_refused(api_key):
    transport = HttpxVisionTransport(transport=httpx.MockTransport(_handler(200, b"{}")))

    async def scenario():
        with pytest.raises(TransportError) as refused:
            await transport.post({"model": "deepseek-flash"}, 0)
        assert refused.value.code == "provider.timeout"

    asyncio.run(scenario())
