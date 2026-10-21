"""Contract for shared offline IdleRecorder."""

from __future__ import annotations

import asyncio

import pytest
from fake_invocation_recorder import IdleRecorder


def test_idle_recorder_refuses_begin_and_finish():
    recorder = IdleRecorder()

    async def scenario() -> None:
        with pytest.raises(AssertionError, match="before a budget check"):
            await recorder.begin_invocation("id")
        with pytest.raises(AssertionError, match="before a budget check"):
            await recorder.finish_invocation("id")

    asyncio.run(scenario())
