"""Monthly AI budget for creation calls (user authorization 2026-11-11: ¥30/month, ¥1/video)."""

from decimal import Decimal

from gamingcreator.application.ai_budget import Spend, call_ceiling_cny, decide
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004 as PRICE


def test_ceiling_bounds_tokens_by_payload_bytes():
    small = call_ceiling_cny(PRICE, "x" * 1000, 2048)
    chinese = call_ceiling_cny(PRICE, "字" * 1000, 2048)  # three UTF-8 bytes each
    assert small < chinese < Decimal("0.03")
    assert call_ceiling_cny(PRICE, "x" * 2_000_000, 2048) == PRICE.reservation_cny(
        PRICE.context_limit_tokens, 2048
    )


def test_within_both_caps_is_allowed():
    rows = [Spend("2026-11", "job", Decimal("0.5")), Spend("2026-10", "old", Decimal("29"))]
    decision = decide(rows, "job", "2026-11", Decimal("0.4"))
    assert decision.allowed and decision.month_spent_cny == Decimal("0.5")


def test_video_cap_counts_every_month_of_that_video():
    rows = [Spend("2026-10", "job", Decimal("0.7"))]
    decision = decide(rows, "job", "2026-11", Decimal("0.4"))
    assert not decision.allowed and "单条" in decision.reason


def test_month_cap_counts_every_video():
    rows = [Spend("2026-11", f"job{i}", Decimal("0.99")) for i in range(30)]
    decision = decide(rows, "new", "2026-11", Decimal("0.4"))
    assert not decision.allowed and "每月" in decision.reason
    assert decision.as_dict()["eligible"] is False
