"""Shared offline VisionTransport doubles for Phase-0 tests (no network)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence

from gamingcreator.infrastructure.http_transport import HttpResponse

type Reply = HttpResponse | Exception
type BeforePost = Callable[[dict[str, object], float], None]


def offline_chat_completion(
    *,
    response_id: str,
    events: list[dict[str, object]] | None = None,
    model: str = "deepseek-flash",
    prompt_tokens: int = 20,
    completion_tokens: int = 3,
    prompt_cache_hit_tokens: int = 2,
    prompt_cache_miss_tokens: int = 18,
) -> HttpResponse:
    """Build a bounded DeepSeek-shaped 200 body used by offline vision tests."""
    body = {
        "id": response_id,
        "model": model,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"events": list(events or [])}),
                },
            }
        ],
    }
    return HttpResponse(200, json.dumps(body).encode("utf-8"))


class FakeVisionTransport:
    """Queue/repeat offline replies; never opens sockets or reads process proxies."""

    def __init__(
        self,
        replies: Sequence[Reply] | None = None,
        *,
        repeat: Reply | None = None,
        before_post: BeforePost | None = None,
    ) -> None:
        self.replies = list(replies or [])
        self.repeat = repeat
        self.before_post = before_post
        self.payloads: list[dict[str, object]] = []

    async def post(self, payload: dict[str, object], timeout_seconds: float) -> HttpResponse:
        if self.before_post is not None:
            self.before_post(payload, timeout_seconds)
        self.payloads.append(payload)
        if self.replies:
            reply: Reply = self.replies.pop(0)
        elif self.repeat is not None:
            reply = self.repeat
        else:
            raise AssertionError("FakeVisionTransport has no remaining offline replies.")
        if isinstance(reply, Exception):
            raise reply
        return reply


class WaitingTransport:
    """Hang on post until cancelled; used for offline cancel/timeout contracts.

    Never opens sockets. Callers wait on ``started`` then cancel the consumer.
    """

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.closed = False

    async def post(self, payload: dict[str, object], timeout_seconds: float) -> HttpResponse:
        del payload, timeout_seconds
        self.started.set()
        try:
            await asyncio.Future[None]()
        finally:
            self.closed = True
        raise AssertionError("Cancelled request cannot complete.")
