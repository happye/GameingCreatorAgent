"""Shared offline invocation-recorder doubles for Phase-0 tests."""

from __future__ import annotations


class IdleRecorder:
    """Refuse begin/finish so budget gates are proven before any recording."""

    async def begin_invocation(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("Invocation was recorded before a budget check.")

    async def finish_invocation(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("Invocation was recorded before a budget check.")
