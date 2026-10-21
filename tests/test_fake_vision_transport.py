"""Contract for shared offline FakeVisionTransport."""

from __future__ import annotations

import asyncio
import json

import pytest
from fake_vision_transport import FakeVisionTransport, offline_chat_completion

from gamingcreator.infrastructure.http_transport import HttpResponse, TransportError


def test_queue_returns_and_records_payloads():
    first = HttpResponse(200, b'{"ok":1}')
    second = HttpResponse(400, b'{"error":true}')
    transport = FakeVisionTransport([first, second])

    async def scenario():
        assert await transport.post({"a": 1}, 1.0) is first
        assert await transport.post({"b": 2}, 1.0) is second

    asyncio.run(scenario())
    assert transport.payloads == [{"a": 1}, {"b": 2}]


def test_repeat_response_does_not_consume():
    reply = offline_chat_completion(response_id="chatcmpl-offline", events=[{"x": 1}])
    transport = FakeVisionTransport(repeat=reply)

    async def scenario():
        one = await transport.post({}, 1.0)
        two = await transport.post({}, 1.0)
        assert one.body == two.body == reply.body

    asyncio.run(scenario())
    assert len(transport.payloads) == 2


def test_exception_reply_is_raised():
    transport = FakeVisionTransport([TransportError("provider.network", True)])

    async def scenario():
        with pytest.raises(TransportError) as refused:
            await transport.post({}, 1.0)
        assert refused.value.code == "provider.network"

    asyncio.run(scenario())


def test_before_post_hook_runs():
    seen: list[object] = []

    def before(payload: dict[str, object], timeout_seconds: float) -> None:
        seen.append((payload, timeout_seconds))

    transport = FakeVisionTransport([HttpResponse(200, b"{}")], before_post=before)
    asyncio.run(transport.post({"q": True}, 2.5))
    assert seen == [({"q": True}, 2.5)]


def test_exhausted_queue_without_repeat_fails_loudly():
    transport = FakeVisionTransport([])

    async def scenario():
        with pytest.raises(AssertionError, match="no remaining offline replies"):
            await transport.post({}, 1.0)

    asyncio.run(scenario())


def test_offline_chat_completion_shape():
    response = offline_chat_completion(
        response_id="chatcmpl-frame-contract-offline",
        events=[{"startFrameId": "f0", "endFrameId": "f1"}],
    )
    assert response.status_code == 200
    decoded = json.loads(response.body)
    assert decoded["id"] == "chatcmpl-frame-contract-offline"
    assert decoded["model"] == "deepseek-flash"
    content = json.loads(decoded["choices"][0]["message"]["content"])
    assert content == {"events": [{"startFrameId": "f0", "endFrameId": "f1"}]}
